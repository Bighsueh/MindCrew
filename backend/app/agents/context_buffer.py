from __future__ import annotations

import json
import logging
import time
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

# Shared overlap-check cache (project-level, TTL 10s)
# Avoids 5 agents each polling sidecar independently every tick
_overlap_cache: dict[str, tuple[float, dict]] = {}
_OVERLAP_CACHE_TTL = 10.0

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


def _normalize_canvas(snapshot: dict, micro_phase: str | None = None) -> dict:
    """Convert Phase 14 spatial-aware snapshot to a unified dict.

    Produces a superset containing BOTH Phase 14 keys (summary, clusters,
    ungrouped_notes, organization_hint) AND legacy keys (total_notes,
    notes, groups, ungrouped) for backward compatibility with scoring functions.
    """
    summary = snapshot.get("summary")
    if not summary:
        return snapshot  # Already legacy format

    result = dict(snapshot)

    # Legacy: total_notes at top level
    result["total_notes"] = summary.get("total_notes", 0)

    # Legacy: notes[] with id/content/author/color/created_at
    spatial_notes = snapshot.get("notes", [])
    result["spatial_notes"] = spatial_notes  # Preserve Phase 14 format
    legacy_notes = []
    for n in spatial_notes:
        legacy_notes.append({
            "id": n.get("id", ""),
            "content": n.get("text", ""),
            "author": n.get("author_name", ""),
            "color": n.get("color", ""),
            "created_at": n.get("created_at", ""),
        })
    result["notes"] = legacy_notes

    # Legacy: groups[] from clusters (semantic clusters as group proxy)
    clusters = snapshot.get("clusters", [])
    cluster_note_map: dict[str, list[str]] = {}
    for n in spatial_notes:
        cid = n.get("cluster_id")
        if cid:
            cluster_note_map.setdefault(cid, []).append(n.get("id", ""))
    legacy_groups = []
    for c in clusters:
        cid = c.get("cluster_id", "")
        legacy_groups.append({
            "name": c.get("suggested_label", cid),
            "notes": cluster_note_map.get(cid, []),
        })
    result["groups"] = legacy_groups

    # Legacy: ungrouped as flat ID list
    ungrouped_notes = snapshot.get("ungrouped_notes", [])
    result["ungrouped"] = [
        u.get("id", "") if isinstance(u, dict) else u
        for u in ungrouped_notes
    ]

    # Inject organization_hint from summary if not already present
    if "organization_hint" not in result:
        from app.canvas.tools_perception import _generate_organization_hint
        from app.canvas.analyzer import CanvasAnalysis
        # Hint is already in snapshot from get_canvas_snapshot → get_canvas_summary
        pass

    return result


async def get_evaluator_canvas(project_id: UUID, micro_phase: str | None = None) -> dict:
    """Lean canvas state for evaluator -- summary + legacy notes.

    Uses get_canvas_summary (~400 tokens) for Phase 14 keys (summary, clusters),
    plus legacy sidecar for full notes list (notes, groups, ungrouped).
    Much lighter than get_canvas_snapshot (~3600 tokens).
    """
    result: dict = {}

    # Phase 14 summary (lightweight)
    try:
        from app.canvas.tools_perception import get_canvas_summary
        summary_data = await get_canvas_summary(project_id, micro_phase=micro_phase)
        result.update(summary_data)
    except Exception:
        pass

    # Legacy sidecar for notes/groups/ungrouped
    try:
        from app.bridge.canvas_ops import canvas_ops
        legacy = await canvas_ops.get_canvas_state(project_id)
        result["total_notes"] = legacy.get("total_notes", 0)
        result["notes"] = legacy.get("notes", [])
        result["ungrouped"] = legacy.get("ungrouped", [])

        # Groups: use tldraw groups if available, otherwise use semantic clusters
        tldraw_groups = legacy.get("groups", [])
        if tldraw_groups:
            result["groups"] = tldraw_groups
        else:
            # All-AI mode: agents don't create tldraw groups.
            # Use semantic clusters as group proxy for scoring functions.
            clusters = result.get("clusters", [])
            notes_list = legacy.get("notes", [])
            result["groups"] = _clusters_to_groups(clusters, notes_list)
    except Exception:
        result.setdefault("total_notes", result.get("summary", {}).get("total_notes", 0))
        result.setdefault("notes", [])
        result.setdefault("groups", [])
        result.setdefault("ungrouped", [])

    return result


def _clusters_to_groups(clusters: list[dict], notes: list[dict]) -> list[dict]:
    """Convert Phase 14 semantic clusters to legacy group format for scoring."""
    if not clusters:
        return []
    # Build note_id → note mapping for cluster membership
    notes_by_id = {n.get("id", ""): n for n in notes if isinstance(n, dict)}
    groups = []
    for c in clusters:
        cid = c.get("cluster_id", "")
        label = c.get("suggested_label", cid)
        # Get note_ids from notes that belong to this cluster
        # (cluster summary doesn't have note_ids, but notes have cluster_id in spatial format)
        # Fallback: use note_count to estimate
        note_ids = c.get("note_ids", [])
        groups.append({
            "name": label,
            "notes": note_ids,
            "note_count": c.get("note_count", len(note_ids)),
        })
    return groups


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

        canvas_state, current_stage, current_micro_phase, stage_duration, seats, project_name, project_description = await self._load_db_state()
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

        # Compute role_status from micro_phase
        role_status_value: str = "normal"
        if current_micro_phase:
            try:
                from app.stages.micro_phases import get_role_status
                role_status_value = get_role_status(current_micro_phase, self._seat_role)
            except (KeyError, Exception):
                role_status_value = "normal"

        # Load active conversation thread
        tracker = ConversationStateTracker(self._project_id)
        active_thread = await tracker.get_thread_context()

        # Load timestamps for ASSESS Rules 2 & 5
        typing_raw = await r.get(f"project:{self._project_id}:human_typing_ts")
        event_raw = await r.get(f"project:{self._project_id}:last_event_ts")

        # Load Blackboard data (graceful fallback if unavailable)
        blackboard = await self._load_blackboard()

        # Load PhaseStrategy (Phase 13)
        phase_strategy_dict: dict | None = None
        if current_micro_phase:
            from app.agents.phase_strategy import get_phase_strategy
            strategy = get_phase_strategy(current_micro_phase)
            if strategy:
                phase_strategy_dict = {
                    "comm_strategy": strategy.comm_strategy,
                    "comm_goal": strategy.comm_goal,
                    "supervisor_mode": strategy.supervisor_mode,
                }

        context: dict = {
            "project_name": project_name,
            "project_description": project_description,
            "canvas_state": canvas_state,
            "recent_chat": recent_chat,
            "current_stage": current_stage,
            "current_micro_phase": current_micro_phase,
            "my_role_status": role_status_value,
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
        if phase_strategy_dict:
            context["phase_strategy"] = phase_strategy_dict
        return context

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
    ) -> tuple[dict, str, str | None, int, list[dict], str, str]:
        """Load canvas notes, project stage info, and seat states from DB."""
        async with async_session_factory() as session:
            # Project stage + ai_contribution
            from app.db.models.project import Project  # local import avoids circular
            project_row = await session.execute(
                select(Project).where(Project.id == self._project_id)
            )
            project = project_row.scalar_one_or_none()
            current_stage = project.current_stage if project else "discover"
            current_micro_phase = project.current_micro_phase if project else None
            project_name = project.name if project else ""
            project_description = (project.description or "") if project else ""

            # Stage duration: prefer micro_phase_history, then stage_history,
            # then project.created_at as last resort. Capped at 120 min.
            stage_duration = 0
            _MAX_DURATION_MINUTES = 120
            if project:
                stage_start: datetime | None = None

                # Priority 1: most recent micro_phase_history entry
                from app.db.models.micro_phase_history import MicroPhaseHistory
                mph_row = await session.execute(
                    select(MicroPhaseHistory)
                    .where(MicroPhaseHistory.project_id == self._project_id)
                    .order_by(MicroPhaseHistory.created_at.desc())
                    .limit(1)
                )
                mph = mph_row.scalar_one_or_none()
                if mph and mph.created_at:
                    stage_start = mph.created_at

                # Priority 2: stage_history transition to current stage
                if stage_start is None:
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
                        stage_start = sh.created_at

                # Priority 3: project creation (last resort)
                if stage_start is None and project.created_at:
                    stage_start = project.created_at

                if stage_start:
                    if stage_start.tzinfo is None:
                        stage_start = stage_start.replace(tzinfo=timezone.utc)
                    delta = datetime.now(timezone.utc) - stage_start
                    stage_duration = min(int(delta.total_seconds() / 60), _MAX_DURATION_MINUTES)

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
                # Add display name for AI seats
                if s.occupant_type == "ai" and s.seat_role:
                    _ROLE_DISPLAY_NAMES = {
                        "supervisor": "AI 引導者",
                        "crew_1": "AI 同理心專家",
                        "crew_2": "AI 結構化專家",
                        "crew_3": "AI 創意專家",
                        "crew_4": "AI 可行性專家",
                    }
                    entry["display_name"] = _ROLE_DISPLAY_NAMES.get(s.seat_role, f"AI {s.seat_role}")
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

            # Canvas state: try spatial-aware perception (Phase 14), fallback to legacy
            canvas_state = await self._load_canvas_perception(micro_phase=current_micro_phase)

        return canvas_state, current_stage, current_micro_phase, stage_duration, seats, project_name, project_description

    async def _load_canvas_perception(self, micro_phase: str | None = None) -> dict:
        """Load canvas state with spatial-aware perception (Phase 14).

        Returns a unified dict containing BOTH Phase 14 keys (summary, clusters,
        organization_hint) AND legacy keys (total_notes, notes, groups, ungrouped)
        so all downstream consumers work without modification.

        Falls back to legacy sidecar state if SpatialAnalyzer fails.
        """
        try:
            from app.canvas.tools_perception import get_canvas_snapshot
            snapshot = await get_canvas_snapshot(self._project_id)
            return _normalize_canvas(snapshot, micro_phase)
        except Exception as exc:
            logger.debug("Spatial perception failed, falling back to legacy: %s", exc)

        # Legacy fallback
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
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(_CHAT_LIMIT)
            )
            messages = rows.scalars().all()
        return [
            {
                "sender": f"{m.sender_name}({'ai' if m.sender_type == 'ai' else 'human'})",
                "sender_id": m.sender_id or "",
                "sender_type": m.sender_type,
                "content": m.content,
                "time": m.created_at.strftime("%H:%M:%S") if m.created_at else "",
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
