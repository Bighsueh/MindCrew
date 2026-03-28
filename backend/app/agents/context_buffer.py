from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select, text

from app.agents.blackboard import BlackboardManager
from app.agents.conversation_state import ConversationStateTracker
from app.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# Redis key templates
_KEY_CANVAS = "project:{project_id}:canvas_events"
_KEY_CHAT = "project:{project_id}:chat_events"
_KEY_FLOW = "project:{project_id}:flow_events"
_KEY_SEAT = "project:{project_id}:seat_events"
_KEY_AGENT_ACTIONS = "project:{project_id}:agent:{agent_id}:actions"

# Buffer size limits per spec §2.1
_CANVAS_LIMIT = 20
_CHAT_LIMIT = 30
_SEAT_LIMIT = 5


class ContextBuffer:
    """Collect and serve recent events for a single agent in a project.

    Uses Redis as the primary fast store and the DB for durable state
    (canvas snapshot, seat records, stage info).
    """

    def __init__(
        self,
        project_id: UUID,
        agent_id: str,
        seat_role: str,
    ) -> None:
        self._project_id = project_id
        self._agent_id = agent_id
        self._seat_role = seat_role
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    # ------------------------------------------------------------------
    # Public event ingestors (called by event handlers / WebSocket layer)
    # ------------------------------------------------------------------

    async def push_canvas_event(self, event: dict) -> None:
        r = await self._get_redis()
        key = _KEY_CANVAS.format(project_id=self._project_id)
        await r.rpush(key, json.dumps(event))
        await r.ltrim(key, -_CANVAS_LIMIT, -1)

    async def push_chat_event(self, event: dict) -> None:
        r = await self._get_redis()
        key = _KEY_CHAT.format(project_id=self._project_id)
        await r.rpush(key, json.dumps(event))
        await r.ltrim(key, -_CHAT_LIMIT, -1)

    async def push_flow_event(self, event: dict) -> None:
        r = await self._get_redis()
        key = _KEY_FLOW.format(project_id=self._project_id)
        await r.rpush(key, json.dumps(event))
        # Flow events: keep all (they are few and important)

    async def push_seat_event(self, event: dict) -> None:
        r = await self._get_redis()
        key = _KEY_SEAT.format(project_id=self._project_id)
        await r.rpush(key, json.dumps(event))
        await r.ltrim(key, -_SEAT_LIMIT, -1)

    async def record_my_action(self, action: dict) -> None:
        r = await self._get_redis()
        key = _KEY_AGENT_ACTIONS.format(
            project_id=self._project_id, agent_id=self._agent_id
        )
        await r.rpush(key, json.dumps(action))
        await r.ltrim(key, -10, -1)

    # ------------------------------------------------------------------
    # Main context retrieval
    # ------------------------------------------------------------------

    async def get_current_context(self) -> dict:
        """Return the full context dict matching the spec §2.1 JSON format."""
        r = await self._get_redis()

        canvas_state, current_stage, stage_duration, seats, project_name, project_description = await self._load_db_state()
        recent_chat = await self._load_chat(r)
        my_recent_actions = await self._load_my_actions(r)

        # Extract seat index from role name (e.g. "crew_2" → 1, "supervisor" → 0)
        seat_index = 0
        role_lower = self._seat_role.lower()
        if role_lower.startswith("crew_"):
            try:
                seat_index = int(role_lower.split("_")[1]) - 1
            except (IndexError, ValueError):
                seat_index = 0

        # Load active conversation thread
        tracker = ConversationStateTracker(self._project_id)
        active_thread = await tracker.get_thread_context()

        # Load timestamps for ASSESS Rules 2 & 5
        typing_raw = await r.get(f"project:{self._project_id}:human_typing_ts")
        event_raw = await r.get(f"project:{self._project_id}:last_event_ts")

        # Load Blackboard data (graceful fallback if unavailable)
        blackboard = await self._load_blackboard()

        return {
            "project_name": project_name,
            "project_description": project_description,
            "canvas_state": canvas_state,
            "recent_chat": recent_chat,
            "current_stage": current_stage,
            "stage_duration_minutes": stage_duration,
            "seats": seats,
            "my_seat": self._seat_role,
            "seat_index": seat_index,
            "my_recent_actions": my_recent_actions,
            "active_thread": active_thread,
            "blackboard": blackboard,
            "_human_typing_timestamp": float(typing_raw) if typing_raw else None,
            "_last_event_time": float(event_raw) if event_raw else None,
        }

    # ------------------------------------------------------------------
    # Blackboard integration (§4.2)
    # ------------------------------------------------------------------

    async def _load_blackboard(self) -> dict:
        """Load Blackboard data for this agent's context.

        Returns a dict with other_agent_intentions, topic_saturation,
        and coordination. Graceful fallback to empty values on failure.
        """
        try:
            bb = BlackboardManager(
                self._project_id, self._agent_id, self._seat_role
            )
            # Share our Redis connection
            bb._redis = await self._get_redis()

            intentions = await bb.read_other_intentions()
            saturation = await bb.read_topic_saturation()
            coordination = await bb.read_coordination()
            directive = await bb.read_coordination_directive()

            return {
                "other_agent_intentions": [
                    i.model_dump(mode="json") for i in intentions
                ],
                "topic_saturation": (
                    saturation.model_dump(mode="json") if saturation else None
                ),
                "coordination": (
                    coordination.model_dump(mode="json") if coordination else None
                ),
                "coordination_directive": (
                    directive.model_dump(mode="json") if directive else None
                ),
            }
        except Exception:
            logger.warning(
                "Failed to load blackboard for %s", self._agent_id, exc_info=True
            )
            return {
                "other_agent_intentions": [],
                "topic_saturation": None,
                "coordination": None,
                "coordination_directive": None,
            }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_db_state(
        self,
    ) -> tuple[dict, str, int, list[dict], str, str]:
        """Load canvas notes, project stage info, and seat states from DB."""
        async with async_session_factory() as session:
            # Project stage + ai_contribution
            from app.db.models.project import Project  # local import avoids circular
            project_row = await session.execute(
                select(Project).where(Project.id == self._project_id)
            )
            project = project_row.scalar_one_or_none()
            current_stage = project.current_stage if project else "discover"
            project_name = project.name if project else ""
            project_description = (project.description or "") if project else ""

            # Stage duration: use the most recent stage_history entry
            # that transitions TO the current stage, or fall back to project.created_at
            stage_duration = 0
            if project:
                from app.db.models.stage_history import StageHistory

                sh_row = await session.execute(
                    select(StageHistory)
                    .where(
                        StageHistory.project_id == self._project_id,
                        StageHistory.to_stage == current_stage,
                    )
                    .order_by(StageHistory.created_at.desc())
                    .limit(1)
                )
                sh = sh_row.scalar_one_or_none()
                if sh and sh.created_at:
                    started = sh.created_at
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    delta = datetime.now(timezone.utc) - started
                    stage_duration = int(delta.total_seconds() / 60)
                elif project.created_at:
                    # No stage history yet — use project creation time
                    created = project.created_at
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    delta = datetime.now(timezone.utc) - created
                    stage_duration = int(delta.total_seconds() / 60)

            # Seats
            from app.db.models.seat import Seat
            seat_rows = await session.execute(
                select(Seat).where(Seat.project_id == self._project_id)
            )
            seats_raw = seat_rows.scalars().all()
            seats: list[dict] = []
            for s in seats_raw:
                entry: dict[str, Any] = {
                    "role": s.seat_role,
                    "type": s.occupant_type,
                }
                if s.agent_id:
                    entry["agent_id"] = s.agent_id
                # Fetch user name if human
                if s.occupant_type == "human" and s.user_id:
                    from app.db.models.user import User
                    u_row = await session.execute(
                        select(User).where(User.id == s.user_id)
                    )
                    u = u_row.scalar_one_or_none()
                    if u:
                        entry["user_name"] = u.display_name
                seats.append(entry)

            # Canvas state: load from Yjs sidecar (source of truth)
            canvas_state = await self._load_canvas_from_sidecar()

        return canvas_state, current_stage, stage_duration, seats, project_name, project_description

    async def _load_canvas_from_sidecar(self) -> dict:
        """Load canvas state from Yjs sidecar (the source of truth)."""
        try:
            from app.bridge.canvas_ops import canvas_ops

            return await canvas_ops.get_canvas_state(self._project_id)
        except Exception as exc:
            logger.warning("Failed to load canvas from sidecar: %s", exc)
            return {"total_notes": 0, "groups": [], "ungrouped": [], "notes": []}

    async def _load_chat(self, r: aioredis.Redis) -> list[dict]:
        """Load recent chat messages from Redis, falling back to DB."""
        key = _KEY_CHAT.format(project_id=self._project_id)
        raw_list = await r.lrange(key, 0, -1)
        if raw_list:
            result = []
            for raw in raw_list:
                try:
                    result.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
            return result

        # Fall back to DB
        async with async_session_factory() as session:
            from app.db.models.message import Message
            rows = await session.execute(
                select(Message)
                .where(Message.project_id == self._project_id)
                .order_by(Message.created_at.desc())
                .limit(_CHAT_LIMIT)
            )
            messages = rows.scalars().all()
        return [
            {
                "sender": f"{m.sender_name}({'ai' if m.sender_type == 'ai' else 'human'})",
                "sender_type": m.sender_type,
                "content": m.content,
                "time": m.created_at.strftime("%H:%M") if m.created_at else "",
            }
            for m in reversed(messages)
        ]

    async def _load_my_actions(self, r: aioredis.Redis) -> list[dict]:
        key = _KEY_AGENT_ACTIONS.format(
            project_id=self._project_id, agent_id=self._agent_id
        )
        raw_list = await r.lrange(key, 0, -1)
        result = []
        for raw in raw_list:
            try:
                result.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        return result

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
