"""SeatManager: handles AI ↔ human seat transitions with agent lifecycle."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select

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
    ) -> None:
        """A human is taking a seat previously held by AI.

        Steps:
        1. Stop the AI agent running on that seat (if any)
        2. AI sends farewell message
        3. Update PostgreSQL seat record
        4. Update Redis seat state
        5. Broadcast SeatChangedEvent
        """
        key = (project_id, seat_role)

        # 1 & 2: stop agent and send farewell (before DB update so the message appears)
        await self._stop_agent_with_farewell(project_id, seat_role)

        # 3. Update PostgreSQL
        async with async_session_factory() as session:
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
            await session.commit()

        # 4. Update Redis seat state
        await self._update_redis_seat(project_id, seat_role, "human", str(user_id))

        # 5. Broadcast
        ai_display_name = self._role_to_display_name(seat_role)
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
    ) -> None:
        """A human is leaving a seat; AI should take over.

        Steps:
        1. Update PostgreSQL seat to AI
        2. Update Redis
        3. Broadcast SeatChangedEvent
        4. Start new AI agent
        5. AI sends greeting + progress summary
        """
        # 1. Update PostgreSQL
        agent_id = f"agent_{seat_role}"
        previous_human_name: str = "（未知使用者）"
        async with async_session_factory() as session:
            result = await session.execute(
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

                user_result = await session.execute(
                    select(User).where(User.id == seat.user_id)
                )
                user_obj = user_result.scalar_one_or_none()
                if user_obj is not None:
                    previous_human_name = user_obj.display_name

            seat.occupant_type = "ai"
            seat.user_id = None
            seat.agent_id = agent_id
            seat.state = "ai_running"
            seat.joined_at = None
            seat.updated_at = datetime.now(timezone.utc)
            await session.commit()

        # 2. Update Redis
        await self._update_redis_seat(project_id, seat_role, "ai", agent_id)

        # 3. Broadcast
        ai_display_name = self._role_to_display_name(seat_role)
        event = SeatChangedEvent(
            project_id=project_id,
            seat_role=seat_role,
            previous_occupant_type="human",
            previous_display_name=previous_human_name,
            current_occupant_type="ai",
            current_display_name=ai_display_name,
        )
        await event_bus.publish(event)

        # 4. Start AI agent
        await self._start_agent(project_id, seat_role, agent_id)

        # 5. Greeting + summary
        await self._send_ai_greeting(project_id, seat_role, agent_id)

        logger.info(
            "Seat %s in project %s released to AI agent %s", seat_role, project_id, agent_id
        )

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
            key = (project_id, seat.seat_role)
            if key in self._agent_tasks and not self._agent_tasks[key].done():
                continue  # already running
            agent_id = seat.agent_id or f"agent_{seat.seat_role}"
            self._restart_counts.pop(key, None)  # reset counter on explicit start
            await self._start_agent(project_id, seat.seat_role, agent_id)

    def get_agent(self, project_id: UUID, seat_role: str) -> Any | None:
        """Return the running BaseAgent instance, if any."""
        return self._agents.get((project_id, seat_role))

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
        agent_name = self._role_to_display_name(seat_role)

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
        task = asyncio.create_task(agent.start(), name=f"agent_{project_id}_{seat_role}")
        self._agent_tasks[key] = task
        task.add_done_callback(
            lambda t, pid=project_id, sr=seat_role, aid=agent_id: (
                self._schedule_recovery(t, pid, sr, aid)
            )
        )
        logger.info("Started agent %s on seat %s project %s", agent_id, seat_role, project_id)

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

        agent_name = self._role_to_display_name(seat_role)
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
    def _role_to_display_name(seat_role: str) -> str:
        mapping = {
            "supervisor": "AI 主持人",
            "crew_1": "AI 成員 1",
            "crew_2": "AI 成員 2",
            "crew_3": "AI 成員 3",
            "crew_4": "AI 成員 4",
        }
        return mapping.get(seat_role, f"AI {seat_role}")


# Singleton instance
seat_manager = SeatManager()
