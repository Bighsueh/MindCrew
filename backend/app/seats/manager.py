"""SeatManager: handles AI ↔ human seat transitions with agent lifecycle."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.seat import Seat
from app.db.session import async_session_factory
from app.events.bus import event_bus
from app.events.types import SeatChangedEvent, ChatMessageEvent

logger = logging.getLogger(__name__)

# Redis key for per-project seat state cache
_SEAT_STATE_KEY = "project:{project_id}:seats"


_MAX_AGENT_RESTARTS = 3


class SeatManager:
    """Manages seat transitions between human and AI occupants.

    Responsibilities:
    - Stop/start AI agents when a human takes/leaves a seat
    - Send appropriate farewell/greeting chat messages from the AI
    - Persist seat state to PostgreSQL + Redis
    - Broadcast SeatChangedEvent
    """

    def __init__(self) -> None:
        # Registry of running agent tasks: (project_id, seat_role) → asyncio.Task
        self._agent_tasks: dict[tuple[UUID, str], asyncio.Task[Any]] = {}
        # Registry of running BaseAgent instances: (project_id, seat_role) → BaseAgent
        self._agents: dict[tuple[UUID, str], Any] = {}
        # Restart counter per seat to prevent infinite restart loops
        self._restart_counts: dict[tuple[UUID, str], int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def assign_human(
        self,
        project_id: UUID,
        seat_role: str,
        user_id: UUID,
        user_name: str,
        session: AsyncSession | None = None,
    ) -> None:
        """A human is taking a seat previously held by AI.

        Steps:
        1. Stop the AI agent running on that seat (if any)
        2. AI sends farewell message
        3. Update PostgreSQL seat record
        4. Update Redis seat state
        5. Broadcast SeatChangedEvent

        If `session` is provided (e.g. from the service layer), it is used
        for the DB update to preserve transactional consistency in tests.
        """
        if seat_role == "supervisor":
            raise ValueError(
                "Supervisor seat is AI-only and cannot be assigned to a human"
            )
        key = (project_id, seat_role)

        # 0: Mark Blackboard intention as inactive (§7.7)
        await self._mark_blackboard_inactive(project_id, seat_role)

        # 1 & 2: stop agent and send farewell (before DB update so the message appears)
        await self._stop_agent_with_farewell(project_id, seat_role)

        # 3. Update PostgreSQL
        if session is not None:
            await self._update_seat_in_session(session, project_id, seat_role, user_id)
        else:
            async with async_session_factory() as own_session:
                await self._update_seat_in_session(own_session, project_id, seat_role, user_id)
                await own_session.commit()

        # 4. Update Redis seat state
        await self._update_redis_seat(project_id, seat_role, "human", str(user_id))

        # 5. Broadcast — pull persona for accurate display name
        persona = await self._fetch_seat_persona(project_id, seat_role)
        ai_display_name = self._role_to_display_name(seat_role, persona)
        event = SeatChangedEvent(
            project_id=project_id,
            seat_role=seat_role,
            previous_occupant_type="ai",
            previous_display_name=ai_display_name,
            current_occupant_type="human",
            current_display_name=user_name,
        )
        await event_bus.publish(event)
        logger.info(
            "Seat %s in project %s assigned to human user %s", seat_role, project_id, user_id
        )

    async def release_human(
        self,
        project_id: UUID,
        seat_role: str,
        session: AsyncSession | None = None,
    ) -> None:
        """A human is leaving a seat.

        若場上仍有其他人類 → AI 立即接手（更新 DB / Redis、廣播、啟動 agent、送 greeting）。
        若場上 0 人類 → 該席位保留 dormant，留作下一位人類的就座暗示；
        AI agent 不啟動、不送 greeting，但仍寫 DB / Redis 並廣播給前端。

        Supervisor 為 AI-only，不會經由此路徑進入 dormant，但守衛仍保留。
        """
        agent_id = f"agent_{seat_role}"
        previous_human_name: str = "（未知使用者）"
        # 是否要保留為 dormant（在 _do_release 內依據剩餘人類數決定）
        keep_dormant = False

        async def _do_release(s: AsyncSession) -> None:
            nonlocal previous_human_name, keep_dormant
            result = await s.execute(
                select(Seat).where(
                    Seat.project_id == project_id,
                    Seat.seat_role == seat_role,
                )
            )
            seat = result.scalar_one_or_none()
            if seat is None:
                logger.error(
                    "release_human: seat %s not found in project %s", seat_role, project_id
                )
                return

            # Capture human display name before clearing
            if seat.user_id is not None:
                from app.db.models.user import User

                user_result = await s.execute(
                    select(User).where(User.id == seat.user_id)
                )
                user_obj = user_result.scalar_one_or_none()
                if user_obj is not None:
                    previous_human_name = user_obj.display_name

            # 計算「扣掉自己」之後仍在場的人類數
            remaining_humans = await self._count_remaining_humans(
                s, project_id, excluding_seat_role=seat_role
            )
            keep_dormant = remaining_humans == 0 and seat_role != "supervisor"

            seat.occupant_type = "ai"
            seat.user_id = None
            seat.joined_at = None
            seat.updated_at = datetime.now(timezone.utc)
            if keep_dormant:
                # 保留給下一位人類的視覺空位
                seat.agent_id = None
                seat.state = "dormant"
            else:
                seat.agent_id = agent_id
                seat.state = "ai_running"

        if session is not None:
            await _do_release(session)
        else:
            async with async_session_factory() as own_session:
                await _do_release(own_session)
                await own_session.commit()

        # Redis：dormant 時也清掉 agent_id，與其他 dormant 座位一致
        await self._update_redis_seat(
            project_id, seat_role, "ai", "" if keep_dormant else agent_id
        )

        # Broadcast — dormant 時 current_display_name 留空，讓前端走 dormant UI 分支
        persona = await self._fetch_seat_persona(project_id, seat_role)
        ai_display_name = "" if keep_dormant else self._role_to_display_name(
            seat_role, persona
        )
        event = SeatChangedEvent(
            project_id=project_id,
            seat_role=seat_role,
            previous_occupant_type="human",
            previous_display_name=previous_human_name,
            current_occupant_type="ai",
            current_display_name=ai_display_name,
        )
        await event_bus.publish(event)

        if keep_dormant:
            logger.info(
                "Seat %s in project %s released; no humans remain → kept dormant",
                seat_role,
                project_id,
            )
            return

        # Start AI agent + greeting + summary
        await self._start_agent(project_id, seat_role, agent_id)
        await self._send_ai_greeting(project_id, seat_role, agent_id)

        logger.info(
            "Seat %s in project %s released to AI agent %s", seat_role, project_id, agent_id
        )

    async def _count_remaining_humans(
        self,
        session: AsyncSession,
        project_id: UUID,
        *,
        excluding_seat_role: str,
    ) -> int:
        """同一 project 內，扣掉指定席位以外，目前仍由人類佔用的席位數。"""
        result = await session.execute(
            select(Seat).where(
                Seat.project_id == project_id,
                Seat.occupant_type == "human",
                Seat.seat_role != excluding_seat_role,
            )
        )
        return len(list(result.scalars().all()))

    async def stop_all_agents(self, project_id: UUID) -> None:
        """Stop all AI agents for a project (e.g. on project close)."""
        for key in list(self._agent_tasks.keys()):
            if key[0] == project_id:
                await self._stop_agent(key[0], key[1])

    async def stop_all(self) -> None:
        """Stop all running agents across all projects (for graceful shutdown)."""
        for key in list(self._agent_tasks.keys()):
            if not key[1].startswith("__recovery_"):
                await self._stop_agent(key[0], key[1])

    async def start_all_agents(self, project_id: UUID) -> None:
        """Start AI agents on all AI-occupied seats for a project.

        Idempotent: skips seats that already have a running task.
        Phase 21: dormant seats are skipped here — they only activate via
        :meth:`activate_dormant_seats` which is triggered by the first
        human joining the project.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(Seat).where(
                    Seat.project_id == project_id,
                    Seat.occupant_type == "ai",
                )
            )
            ai_seats = result.scalars().all()

        for seat in ai_seats:
            if seat.state == "dormant":
                continue  # Phase 21: not yet activated
            key = (project_id, seat.seat_role)
            if key in self._agent_tasks and not self._agent_tasks[key].done():
                continue  # already running
            agent_id = seat.agent_id or f"agent_{seat.seat_role}"
            self._restart_counts.pop(key, None)  # reset counter on explicit start
            await self._start_agent(project_id, seat.seat_role, agent_id)

    async def activate_dormant_seats(
        self,
        project_id: UUID,
        *,
        crew_stagger_seconds: float = 1.0,
        session: AsyncSession | None = None,
    ) -> None:
        """Phase 21: 第一位真人入座後，把所有 dormant AI 席位轉為 active。

        - Supervisor 立即啟動（含 greeting），使用呼叫端 ``session``（若提供），
          以便和外層交易共用 visibility（測試 fixture 不 commit 時必要）。
        - 其他 dormant crew seats 在 ``crew_stagger_seconds`` 間距內依序啟動，
          並在 background task 中執行（用自己的 session）以避免阻塞 HTTP 回應。
        """
        if session is not None:
            result = await session.execute(
                select(Seat).where(
                    Seat.project_id == project_id,
                    Seat.occupant_type == "ai",
                    Seat.state == "dormant",
                )
            )
            dormant_seats = list(result.scalars().all())
        else:
            async with async_session_factory() as own_session:
                result = await own_session.execute(
                    select(Seat).where(
                        Seat.project_id == project_id,
                        Seat.occupant_type == "ai",
                        Seat.state == "dormant",
                    )
                )
                dormant_seats = list(result.scalars().all())

        if not dormant_seats:
            return

        supervisor_seat = next(
            (s for s in dormant_seats if s.seat_role == "supervisor"), None
        )
        crew_seats = [s for s in dormant_seats if s.seat_role != "supervisor"]
        crew_seats.sort(key=lambda s: s.seat_role)  # crew_1, crew_2, ...

        if supervisor_seat is not None:
            await self._promote_dormant_seat(
                project_id, supervisor_seat.seat_role, session=session
            )

        async def _stagger_crew() -> None:
            for idx, seat in enumerate(crew_seats):
                await asyncio.sleep(crew_stagger_seconds * (idx + 1))
                try:
                    # Background path: 使用自己的 session（外層 request 已結束）。
                    await self._promote_dormant_seat(project_id, seat.seat_role)
                except Exception as exc:  # pragma: no cover - background safety
                    logger.warning(
                        "activate_dormant_seats(crew=%s) failed: %s", seat.seat_role, exc
                    )

        if crew_seats:
            asyncio.create_task(_stagger_crew())

    async def _promote_dormant_seat(
        self,
        project_id: UUID,
        seat_role: str,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Flip a single seat from dormant → ai_running, start its agent, and broadcast.

        若提供 ``session`` 則沿用之（不 commit，交給外層）；否則開新 session 並 commit。
        """
        agent_id = f"agent_{seat_role}"

        async def _flip(s: AsyncSession, commit: bool) -> bool:
            result = await s.execute(
                select(Seat).where(
                    Seat.project_id == project_id,
                    Seat.seat_role == seat_role,
                )
            )
            seat = result.scalar_one_or_none()
            if seat is None or seat.state != "dormant":
                return False
            seat.agent_id = agent_id
            seat.state = "ai_running"
            seat.updated_at = datetime.now(timezone.utc)
            if commit:
                await s.commit()
            else:
                await s.flush()
            return True

        if session is not None:
            if not await _flip(session, commit=False):
                return
        else:
            async with async_session_factory() as own_session:
                if not await _flip(own_session, commit=True):
                    return

        await self._update_redis_seat(project_id, seat_role, "ai", agent_id)

        # Broadcast so frontends switch the seat from "待加入" → "代理中".
        persona = await self._fetch_seat_persona(project_id, seat_role)
        ai_display_name = self._role_to_display_name(seat_role, persona)
        event = SeatChangedEvent(
            project_id=project_id,
            seat_role=seat_role,
            previous_occupant_type="ai",
            previous_display_name="",
            current_occupant_type="ai",
            current_display_name=ai_display_name,
        )
        await event_bus.publish(event)

        # Spin up the agent task and let it greet.
        await self._start_agent(project_id, seat_role, agent_id)
        await self._send_ai_greeting(project_id, seat_role, agent_id)
        logger.info(
            "Seat %s in project %s promoted from dormant → ai_running",
            seat_role,
            project_id,
        )

    def get_agent(self, project_id: UUID, seat_role: str) -> Any | None:
        """Return the running BaseAgent instance, if any."""
        return self._agents.get((project_id, seat_role))

    async def restart_agent(
        self, project_id: UUID, seat_role: str
    ) -> None:
        """Stop and re-start the agent for a seat (e.g. after persona update)."""
        key = (project_id, seat_role)
        if key in self._agents:
            await self._stop_agent(project_id, seat_role)
        async with async_session_factory() as session:
            result = await session.execute(
                select(Seat).where(
                    Seat.project_id == project_id,
                    Seat.seat_role == seat_role,
                )
            )
            seat = result.scalar_one_or_none()
        if seat is None or seat.occupant_type != "ai":
            return
        agent_id = seat.agent_id or f"agent_{seat_role}"
        self._restart_counts.pop(key, None)
        await self._start_agent(project_id, seat_role, agent_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _stop_agent_with_farewell(
        self, project_id: UUID, seat_role: str
    ) -> None:
        """Stop agent gracefully, then have it send a farewell message."""
        key = (project_id, seat_role)
        agent = self._agents.get(key)

        if agent is not None:
            # Send farewell before stopping
            farewell = "歡迎加入！我先讓出這個位置，有需要可以隨時叫我回來。"
            await self._publish_chat(project_id, f"agent_{seat_role}", agent._agent_name, farewell)
            await agent.stop()

        # Cancel the task and wait for cleanup
        task = self._agent_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        self._agents.pop(key, None)

    async def _stop_agent(self, project_id: UUID, seat_role: str) -> None:
        """Stop agent without sending any message."""
        key = (project_id, seat_role)
        agent = self._agents.get(key)
        if agent is not None:
            await agent.stop()

        task = self._agent_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        self._agents.pop(key, None)

    async def _start_agent(
        self, project_id: UUID, seat_role: str, agent_id: str
    ) -> None:
        """Instantiate and start a BaseAgent for the given seat."""
        from app.agents.base_agent import BaseAgent

        # Resolve ai_contribution from project
        ai_contribution = await self._get_ai_contribution(project_id)
        is_supervisor = seat_role == "supervisor"
        persona = await self._fetch_seat_persona(project_id, seat_role)
        agent_name = self._role_to_display_name(seat_role, persona)

        agent = BaseAgent(
            project_id=project_id,
            agent_id=agent_id,
            seat_role=seat_role,
            agent_name=agent_name,
            ai_contribution=ai_contribution,
            is_supervisor=is_supervisor,
        )
        key = (project_id, seat_role)
        self._agents[key] = agent
        # Seed last_event_ts for fresh projects so ASSESS Rule 5 can fire
        await self._seed_last_event_ts(project_id)

        task = asyncio.create_task(agent.start(), name=f"agent_{project_id}_{seat_role}")
        self._agent_tasks[key] = task
        task.add_done_callback(
            lambda t, pid=project_id, sr=seat_role, aid=agent_id: (
                self._schedule_recovery(t, pid, sr, aid)
            )
        )
        logger.info("Started agent %s on seat %s project %s", agent_id, seat_role, project_id)

    async def _seed_last_event_ts(self, project_id: UUID) -> None:
        """Seed last_event_ts for fresh projects so ASSESS Rule 5 can fire.

        Uses NX (SET-if-Not-exists) to avoid overwriting active projects.
        """
        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                key = f"project:{project_id}:last_event_ts"
                await r.set(key, str(time.time()), nx=True)
            finally:
                await r.aclose()
        except Exception as exc:
            logger.warning("Failed to seed last_event_ts: %s", exc)

    def _schedule_recovery(
        self,
        task: asyncio.Task[Any],
        project_id: UUID,
        seat_role: str,
        agent_id: str,
    ) -> None:
        """Synchronous done_callback: schedule async recovery and keep a reference."""
        recovery = asyncio.create_task(
            self._on_agent_task_done(task, project_id, seat_role, agent_id),
            name=f"recovery_{project_id}_{seat_role}",
        )
        # Store reference so GC doesn't collect the task before it finishes
        self._agent_tasks[(project_id, f"__recovery_{seat_role}")] = recovery

    async def _on_agent_task_done(
        self,
        task: asyncio.Task[Any],
        project_id: UUID,
        seat_role: str,
        agent_id: str,
    ) -> None:
        """Handle agent task completion. Restart if it died unexpectedly."""
        key = (project_id, seat_role)
        cleanup_keys = [key, (project_id, f"__recovery_{seat_role}")]

        # Determine exception (if any)
        if task.cancelled():
            exc = None
        else:
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                exc = None

        # Clean up registries
        for k in cleanup_keys:
            self._agents.pop(k, None)
            self._agent_tasks.pop(k, None)

        if exc is None:
            return  # clean exit or intentional cancellation

        # Unexpected crash — attempt restart with limit
        count = self._restart_counts.get(key, 0)
        if count >= _MAX_AGENT_RESTARTS:
            logger.error(
                "Agent %s on seat %s exceeded max restarts (%d), giving up",
                agent_id, seat_role, _MAX_AGENT_RESTARTS,
            )
            return

        logger.error(
            "Agent %s on seat %s crashed: %s. Restarting (%d/%d) in 5s...",
            agent_id, seat_role, exc, count + 1, _MAX_AGENT_RESTARTS,
        )
        await asyncio.sleep(5.0)

        # Only restart if seat is still AI-occupied
        async with async_session_factory() as session:
            result = await session.execute(
                select(Seat).where(
                    Seat.project_id == project_id,
                    Seat.seat_role == seat_role,
                )
            )
            seat = result.scalar_one_or_none()
            if seat and seat.occupant_type == "ai":
                self._restart_counts[key] = count + 1
                await self._start_agent(project_id, seat_role, agent_id)

    async def _send_ai_greeting(
        self, project_id: UUID, seat_role: str, agent_id: str
    ) -> None:
        """Send greeting and progress summary after AI takes over a seat."""
        from app.seats.seat_progress import (
            build_regular_progress_summary,
            build_supervisor_progress_summary,
        )

        persona = await self._fetch_seat_persona(project_id, seat_role)
        agent_name = self._role_to_display_name(seat_role, persona)
        await self._publish_chat(
            project_id, agent_id, agent_name, "我來接手了！讓我先看看目前的進度…"
        )
        await asyncio.sleep(2.0)

        if seat_role == "supervisor":
            progress_msg = await build_supervisor_progress_summary(project_id)
        else:
            progress_msg = await build_regular_progress_summary(project_id)
        await self._publish_chat(project_id, agent_id, agent_name, progress_msg)

    async def _publish_chat(
        self,
        project_id: UUID,
        sender_id: str,
        sender_name: str,
        content: str,
    ) -> None:
        """Publish a chat message to the event bus and persist to DB."""
        try:
            from app.chinese.converter import chinese_converter
            content = chinese_converter.convert(content)
        except Exception as exc:
            logger.warning("Chinese converter failed, using original content: %s", exc)

        try:
            event = ChatMessageEvent(
                project_id=project_id,
                sender_id=sender_id,
                sender_type="ai",
                sender_name=sender_name,
                content=content,
            )
            await event_bus.publish(event)

            # Persist to DB
            from app.db.models.message import Message
            from app.db.models.project import Project

            async with async_session_factory() as session:
                p_result = await session.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = p_result.scalar_one_or_none()
                stage = project.current_stage if project else "discover"

                msg = Message(
                    project_id=project_id,
                    sender_type="ai",
                    sender_id=sender_id,
                    sender_name=sender_name,
                    content=content,
                    stage=stage,
                )
                session.add(msg)
                await session.commit()
        except Exception as exc:
            logger.error("Failed to publish AI chat message: %s", exc)

    async def _update_redis_seat(
        self,
        project_id: UUID,
        seat_role: str,
        occupant_type: str,
        occupant_id: str,
    ) -> None:
        """Update the seat state hash in Redis."""
        try:
            import json as json_module

            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            key = _SEAT_STATE_KEY.format(project_id=project_id)
            await r.hset(
                key,
                seat_role,
                json_module.dumps(
                    {
                        "seat_role": seat_role,
                        "occupant_type": occupant_type,
                        "occupant_id": occupant_id,
                    }
                ),
            )
            await r.expire(key, 86400)  # 24 h TTL
            await r.aclose()
        except Exception as exc:
            logger.warning("Failed to update Redis seat state: %s", exc)

    async def _get_ai_contribution(self, project_id: UUID) -> str:
        """Fetch ai_contribution setting from the project."""
        try:
            from app.db.models.project import Project

            async with async_session_factory() as session:
                result = await session.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = result.scalar_one_or_none()
                if project:
                    return project.ai_contribution
        except Exception as exc:
            logger.warning("Failed to fetch ai_contribution: %s", exc)
        return "medium"

    @staticmethod
    async def _update_seat_in_session(
        session: AsyncSession, project_id: UUID, seat_role: str, user_id: UUID
    ) -> None:
        """Update seat record to human occupant within the given session."""
        result = await session.execute(
            select(Seat).where(
                Seat.project_id == project_id,
                Seat.seat_role == seat_role,
            )
        )
        seat = result.scalar_one_or_none()
        if seat is None:
            logger.error(
                "assign_human: seat %s not found in project %s", seat_role, project_id
            )
            return
        seat.occupant_type = "human"
        seat.user_id = user_id
        seat.agent_id = None
        seat.state = "human_active"
        seat.joined_at = datetime.now(timezone.utc)
        seat.updated_at = datetime.now(timezone.utc)

    @staticmethod
    async def _mark_blackboard_inactive(project_id: UUID, seat_role: str) -> None:
        """Mark a seat's Blackboard intention as inactive (human takeover, §7.7)."""
        try:
            from app.agents.blackboard import BlackboardManager

            agent_id = f"agent_{seat_role}"
            bb = BlackboardManager(project_id, agent_id, seat_role)
            await bb.mark_inactive()
        except Exception as exc:
            logger.warning(
                "Failed to mark blackboard inactive for %s: %s", seat_role, exc
            )

    @staticmethod
    def _role_to_display_name(seat_role: str, persona: dict | None = None) -> str:
        """Resolve display name with persona-aware lookup (Phase 19).

        ``persona`` is the JSONB payload stored on the seat. When supplied
        the persona's name takes precedence over legacy capability labels.
        """
        from app.agents.personas.display import resolve_display_name

        return resolve_display_name(seat_role, persona)

    async def _fetch_seat_persona(
        self, project_id: UUID, seat_role: str
    ) -> dict | None:
        """Read seat.persona JSONB from DB. Returns None on miss/error."""
        try:
            from app.db.models.seat import Seat

            async with async_session_factory() as session:
                result = await session.execute(
                    select(Seat).where(
                        Seat.project_id == project_id,
                        Seat.seat_role == seat_role,
                    )
                )
                seat = result.scalar_one_or_none()
                if seat is None:
                    return None
                return getattr(seat, "persona", None)
        except Exception as exc:
            logger.debug(
                "Failed to fetch persona for %s/%s: %s",
                project_id,
                seat_role,
                exc,
            )
            return None


# Singleton instance
seat_manager = SeatManager()
