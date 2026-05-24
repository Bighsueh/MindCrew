"""統一版 ``backend/app/agents/context_buffer.py`` —— Phase 17/18/19/20 合併目標。

本檔不是執行檔，是 **合併參考**。
合併 SOP（見 `prompts/phases/PHASE_MERGE_PLAN.md` §3）的最後一步，
把本檔複製到 ``backend/app/agents/context_buffer.py`` 取代衝突檔。

設計原則：
1. **由位置耦合改為命名耦合**
   ``_load_db_state`` 從 7-tuple 變為 :class:`ProjectStateSnapshot` dataclass。
   未來任何 Phase 要加欄位，只要在 dataclass 多一行，不再撞 tuple unpack。
2. **每個 Phase 的貢獻分離為獨立 helper**
   - Phase 17 → ``_load_sub_phase_frame``
   - Phase 19 → ``_load_persona_frame`` + ``_resolve_ai_display_name``
   - Phase 20 → ``_load_chat`` 內加 ``group_only_filter`` + ``get_role_status`` 簽章相容
3. **Feature-detection import**
   每個 Phase 的新模組（``sub_phases``、``personas.display``、``message_filters``、
   ``timer.service``、``reveal_queue``、``personas`` field on Seat）用 try/except 包，
   讓本檔在合到一半（例如只合了 Phase 17，還沒合 19/20）時也能正常 import。
   合完之後可選擇「移除 try/except 改為硬 import」做最後 polish。

如此三個 session 的 vibe 目的全部保留：
- confident-taussig 的 sub-phase / comm_mode / zones / reveal-queue / timer pct
- sad-mcclintock 的 persona snapshot + 動態 display name + seats-aware role_status
- vigorous-bose 的 group_only_filter（不外洩 personal chat）
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select

from app.agents.blackboard import BlackboardManager
from app.agents.conversation_state import ConversationStateTracker
from app.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis key templates + buffer size limits (unchanged from main)
# ---------------------------------------------------------------------------
_KEY_CANVAS = "project:{project_id}:canvas_events"
_KEY_CHAT = "project:{project_id}:chat_events"
_KEY_FLOW = "project:{project_id}:flow_events"
_KEY_SEAT = "project:{project_id}:seat_events"
_KEY_AGENT_ACTIONS = "project:{project_id}:agent:{agent_id}:actions"

_CANVAS_LIMIT = 20
_CHAT_LIMIT = 30
_SEAT_LIMIT = 5

# Legacy fallback used when Phase 19 personas/display module is not yet merged.
_LEGACY_AI_DISPLAY_NAMES = {
    "supervisor": "AI 引導者",
    "crew_1": "AI 同理心專家",
    "crew_2": "AI 結構化專家",
    "crew_3": "AI 創意專家",
    "crew_4": "AI 可行性專家",
}


# ---------------------------------------------------------------------------
# Dataclass snapshots — extension points each Phase plugs into
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectStateSnapshot:
    """Core project state loaded from DB.

    Future Phase additions: just add an Optional field with a default;
    no tuple-positions to renumber.
    """

    canvas_state: dict
    current_stage: str
    current_micro_phase: str | None
    stage_duration_minutes: int
    seats: list[dict]
    project_name: str
    project_description: str
    # Phase 17 — sticky-only sub-phase pointer
    current_sub_phase: str | None = None
    # Phase 27 — 建立時使用者勾選的利害關係人（Discover 階段 prompt 注入素材）
    stakeholders: list[dict] = field(default_factory=list)
    task_brief_kind: str = "legacy"


@dataclass(frozen=True)
class SubPhaseFrame:
    """Phase 17 — sticky-only-strategy derived context.

    All fields default to neutral values so build_context can splat
    ``frame.__dict__`` into the context dict regardless of whether
    Phase 17 is merged yet.
    """

    current_sub_phase: str | None = None
    comm_mode: str = "discussion"
    active_zones: list[str] = field(default_factory=list)
    reveal_queue: list[str] = field(default_factory=list)
    time_budget_used_pct: float = 0.0


@dataclass(frozen=True)
class PersonaFrame:
    """Phase 19 — per-agent persona snapshot."""

    my_persona: dict | None = None


# ---------------------------------------------------------------------------
# Canvas helpers (kept verbatim from main — irrelevant to the 3-way merge)
# ---------------------------------------------------------------------------


def _normalize_canvas(snapshot: dict, micro_phase: str | None = None) -> dict:
    summary = snapshot.get("summary")
    if not summary:
        return snapshot

    result = dict(snapshot)
    result["total_notes"] = summary.get("total_notes", 0)

    _ARCHIVE_ROW_THRESHOLD = 21
    all_spatial_notes = snapshot.get("notes", [])
    spatial_notes = [
        n for n in all_spatial_notes
        if n.get("grid_position", [0, 0])[1] < _ARCHIVE_ROW_THRESHOLD
    ]
    result["spatial_notes"] = spatial_notes

    legacy_notes = [
        {
            "id": n.get("id", ""),
            "content": n.get("text", ""),
            "author": n.get("author_name", ""),
            "color": n.get("color", ""),
            "created_at": n.get("created_at", ""),
        }
        for n in spatial_notes
    ]
    result["notes"] = legacy_notes

    clusters = snapshot.get("clusters", [])
    cluster_note_map: dict[str, list[str]] = {}
    for n in spatial_notes:
        cid = n.get("cluster_id")
        if cid:
            cluster_note_map.setdefault(cid, []).append(n.get("id", ""))
    result["groups"] = [
        {
            "name": c.get("suggested_label", c.get("cluster_id", "")),
            "notes": cluster_note_map.get(c.get("cluster_id", ""), []),
        }
        for c in clusters
    ]

    ungrouped_notes = snapshot.get("ungrouped_notes", [])
    result["ungrouped"] = [
        u.get("id", "") if isinstance(u, dict) else u for u in ungrouped_notes
    ]
    return result


async def get_evaluator_canvas(project_id: UUID, micro_phase: str | None = None) -> dict:
    """Lean canvas state for evaluator (unchanged from main)."""
    result: dict = {}
    try:
        from app.canvas.tools_perception import get_canvas_summary
        result.update(await get_canvas_summary(project_id, micro_phase=micro_phase))
    except Exception:
        pass

    try:
        from app.bridge.canvas_ops import canvas_ops
        legacy = await canvas_ops.get_canvas_state(project_id)
        result["total_notes"] = legacy.get("total_notes", 0)
        result["notes"] = legacy.get("notes", [])
        result["ungrouped"] = legacy.get("ungrouped", [])
        tldraw_groups = legacy.get("groups", [])
        if tldraw_groups:
            result["groups"] = tldraw_groups
        else:
            clusters = result.get("clusters", [])
            result["groups"] = _clusters_to_groups(clusters, legacy.get("notes", []))
    except Exception:
        result.setdefault("total_notes", result.get("summary", {}).get("total_notes", 0))
        result.setdefault("notes", [])
        result.setdefault("groups", [])
        result.setdefault("ungrouped", [])
    return result


def _clusters_to_groups(clusters: list[dict], notes: list[dict]) -> list[dict]:
    if not clusters:
        return []
    return [
        {
            "name": c.get("suggested_label", c.get("cluster_id", "")),
            "notes": c.get("note_ids", []),
            "note_count": c.get("note_count", len(c.get("note_ids", []))),
        }
        for c in clusters
    ]


# ---------------------------------------------------------------------------
# ContextBuffer
# ---------------------------------------------------------------------------


class ContextBuffer:
    """Collect and serve recent events for a single agent in a project."""

    def __init__(self, project_id: UUID, agent_id: str, seat_role: str) -> None:
        self._project_id = project_id
        self._agent_id = agent_id
        self._seat_role = seat_role
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    # -------- Public event ingestors --------

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

    # -------- Main context retrieval --------

    async def get_current_context(self) -> dict:
        """Return the full context dict matching the spec §2.1 JSON format."""
        r = await self._get_redis()

        state = await self._load_db_state()
        recent_chat = await self._load_chat(r)
        my_recent_actions = await self._load_my_actions(r)

        seat_index = self._extract_seat_index(self._seat_role)
        role_status_value = self._compute_role_status(
            state.current_micro_phase, state.seats
        )

        tracker = ConversationStateTracker(self._project_id)
        active_thread = await tracker.get_thread_context()

        typing_raw = await r.get(f"project:{self._project_id}:human_typing_ts")
        event_raw = await r.get(f"project:{self._project_id}:last_event_ts")

        blackboard = await self._load_blackboard()
        phase_strategy_dict = self._load_phase_strategy_dict(state.current_micro_phase)

        # Phase 17 — sub-phase / comm_mode / zones / reveal queue / timer
        sub_phase_frame = await self._load_sub_phase_frame(state.current_sub_phase)

        # Phase 19 — persona snapshot for this seat
        persona_frame = self._load_persona_frame(state.seats)

        context: dict = {
            # Core (always present)
            "project_name": state.project_name,
            "project_description": state.project_description,
            "canvas_state": state.canvas_state,
            "recent_chat": recent_chat,
            "current_stage": state.current_stage,
            "current_micro_phase": state.current_micro_phase,
            "my_role_status": role_status_value,
            "stage_duration_minutes": state.stage_duration_minutes,
            "seats": state.seats,
            "my_seat": self._seat_role,
            "seat_index": seat_index,
            "my_recent_actions": my_recent_actions,
            "active_thread": active_thread,
            "blackboard": blackboard,
            "_human_typing_timestamp": float(typing_raw) if typing_raw else None,
            "_last_event_time": float(event_raw) if event_raw else None,
            # Phase 17 fields
            "current_sub_phase": sub_phase_frame.current_sub_phase,
            "comm_mode": sub_phase_frame.comm_mode,
            "active_zones": sub_phase_frame.active_zones,
            "reveal_queue": sub_phase_frame.reveal_queue,
            "time_budget_used_pct": sub_phase_frame.time_budget_used_pct,
            # Phase 19 fields
            "my_persona": persona_frame.my_persona,
            # Phase 27 fields — 建立時勾選的利害關係人（Discover 階段使用）
            "stakeholders": state.stakeholders,
            "task_brief_kind": state.task_brief_kind,
        }
        if phase_strategy_dict:
            context["phase_strategy"] = phase_strategy_dict

        # specs/16-timer-system.md §6.5.4：把時間壓力等級 + 階段意圖塞進
        # context，讓 serializer / supervisor triggers / crew prompts 都
        # 能讀取，不必各自重算。
        try:
            from app.stages.phase_intent import get_phase_intent
            from app.timer.pressure import compute_pressure_level

            context["phase_intent"] = get_phase_intent(state.current_micro_phase)
            context["time_pressure_level"] = compute_pressure_level(
                sub_phase_frame.time_budget_used_pct
            )
        except Exception:
            logger.debug("phase_intent/pressure injection failed", exc_info=True)

        return context

    # -------- Phase-specific helpers --------

    @staticmethod
    def _extract_seat_index(seat_role: str) -> int:
        role_lower = seat_role.lower()
        if role_lower.startswith("crew_"):
            try:
                return int(role_lower.split("_")[1]) - 1
            except (IndexError, ValueError):
                return 0
        return 0

    def _compute_role_status(
        self, current_micro_phase: str | None, seats: list[dict]
    ) -> str:
        """Compute role_status with Phase 19 seats-aware fallback.

        Phase 19 changed ``get_role_status`` signature to accept ``seats=``.
        We detect via introspection so this code works on both pre-19 and
        post-19 codebases without conditional imports.
        """
        if not current_micro_phase:
            return "normal"
        try:
            from app.stages.micro_phases import get_role_status
            try:
                sig = inspect.signature(get_role_status)
                if "seats" in sig.parameters:
                    return get_role_status(
                        current_micro_phase, self._seat_role, seats=seats
                    )
            except (TypeError, ValueError):
                pass
            return get_role_status(current_micro_phase, self._seat_role)
        except KeyError:
            return "normal"
        except Exception:
            logger.debug(
                "role_status fallback for %s/%s", current_micro_phase, self._seat_role,
                exc_info=True,
            )
            return "normal"

    def _load_phase_strategy_dict(self, current_micro_phase: str | None) -> dict | None:
        if not current_micro_phase:
            return None
        try:
            from app.agents.phase_strategy import get_phase_strategy
            strategy = get_phase_strategy(current_micro_phase)
        except Exception:
            return None
        if not strategy:
            return None
        return {
            "comm_strategy": strategy.comm_strategy,
            "comm_goal": strategy.comm_goal,
            "supervisor_mode": strategy.supervisor_mode,
        }

    async def _load_sub_phase_frame(
        self, current_sub_phase: str | None
    ) -> SubPhaseFrame:
        """Phase 17 — derive comm_mode / zones / reveal queue / timer pct.

        Every dependency is feature-detected; missing modules → neutral defaults.
        """
        if not current_sub_phase:
            return SubPhaseFrame()

        comm_mode = "discussion"
        active_zones: list[str] = []
        try:
            from app.stages.sub_phases import get_sub_phase
            sp = get_sub_phase(current_sub_phase)
            comm_mode = sp.comm_modes[0] if sp.comm_modes else "discussion"
            active_zones = list(sp.zones)
        except (ImportError, KeyError):
            pass

        reveal_queue: list[str] = []
        try:
            from app.agents.reveal_queue import get_queue
            reveal_queue = await get_queue(self._project_id)
        except ImportError:
            pass
        except Exception:
            logger.debug("reveal_queue lookup failed", exc_info=True)

        time_budget_used_pct = 0.0
        try:
            from app.timer.service import TimerService
            time_budget_used_pct = await TimerService.get_used_pct(self._project_id)
        except ImportError:
            pass
        except Exception:
            logger.debug("TimerService lookup failed", exc_info=True)

        return SubPhaseFrame(
            current_sub_phase=current_sub_phase,
            comm_mode=comm_mode,
            active_zones=active_zones,
            reveal_queue=reveal_queue,
            time_budget_used_pct=time_budget_used_pct,
        )

    def _load_persona_frame(self, seats: list[dict]) -> PersonaFrame:
        """Phase 19 — find this agent's persona snapshot inside the seats list."""
        for seat_entry in seats:
            if (
                seat_entry.get("role") == self._seat_role
                or seat_entry.get("seat_role") == self._seat_role
            ):
                return PersonaFrame(my_persona=seat_entry.get("persona"))
        return PersonaFrame()

    @staticmethod
    def _resolve_ai_display_name(seat_role: str, persona: Any) -> str:
        """Phase 19 — prefer persona-driven name, fall back to legacy table."""
        try:
            from app.agents.personas.display import resolve_display_name
            return resolve_display_name(seat_role, persona)
        except ImportError:
            return _LEGACY_AI_DISPLAY_NAMES.get(seat_role, f"AI {seat_role}")
        except Exception:
            logger.debug("resolve_display_name failed for %s", seat_role, exc_info=True)
            return _LEGACY_AI_DISPLAY_NAMES.get(seat_role, f"AI {seat_role}")

    # -------- Blackboard --------

    async def _load_blackboard(self) -> dict:
        try:
            bb = BlackboardManager(self._project_id, self._agent_id, self._seat_role)
            bb._redis = await self._get_redis()
            intentions = await bb.read_other_intentions()
            saturation = await bb.read_topic_saturation()
            coordination = await bb.read_coordination()
            directive = await bb.read_coordination_directive()
            return {
                "other_agent_intentions": [i.model_dump(mode="json") for i in intentions],
                "topic_saturation": saturation.model_dump(mode="json") if saturation else None,
                "coordination": coordination.model_dump(mode="json") if coordination else None,
                "coordination_directive": directive.model_dump(mode="json") if directive else None,
            }
        except Exception:
            logger.warning("Failed to load blackboard for %s", self._agent_id, exc_info=True)
            return {
                "other_agent_intentions": [],
                "topic_saturation": None,
                "coordination": None,
                "coordination_directive": None,
            }

    # -------- DB load --------

    async def _load_db_state(self) -> ProjectStateSnapshot:
        async with async_session_factory() as session:
            from app.db.models.project import Project
            from app.db.models.seat import Seat

            project_row = await session.execute(
                select(Project).where(Project.id == self._project_id)
            )
            project = project_row.scalar_one_or_none()
            current_stage = project.current_stage if project else "discover"
            current_micro_phase = project.current_micro_phase if project else None
            project_name = project.name if project else ""
            project_description = (project.description or "") if project else ""
            # Phase 17 — optional column
            current_sub_phase = (
                getattr(project, "current_sub_phase", None) if project else None
            )
            # Phase 27 — stakeholders 是 list[dict]，舊 project 為 []
            stakeholders_raw = (
                list(project.stakeholders or []) if project else []
            )
            task_brief_kind = (
                getattr(project, "task_brief_kind", "legacy") if project else "legacy"
            )

            stage_duration = await self._compute_stage_duration(
                session, project, current_stage
            )

            seat_rows = await session.execute(
                select(Seat).where(Seat.project_id == self._project_id)
            )
            seats = [
                await self._build_seat_entry(session, s) for s in seat_rows.scalars().all()
            ]

            canvas_state = await self._load_canvas_perception(
                micro_phase=current_micro_phase
            )

        return ProjectStateSnapshot(
            canvas_state=canvas_state,
            current_stage=current_stage,
            current_micro_phase=current_micro_phase,
            stage_duration_minutes=stage_duration,
            seats=seats,
            project_name=project_name,
            project_description=project_description,
            current_sub_phase=current_sub_phase,
            stakeholders=stakeholders_raw,
            task_brief_kind=task_brief_kind,
        )

    async def _compute_stage_duration(
        self, session, project, current_stage: str
    ) -> int:
        _MAX_DURATION_MINUTES = 120
        if not project:
            return 0

        stage_start: datetime | None = None

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

        if stage_start is None and project.created_at:
            stage_start = project.created_at

        if not stage_start:
            return 0
        if stage_start.tzinfo is None:
            stage_start = stage_start.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - stage_start
        return min(int(delta.total_seconds() / 60), _MAX_DURATION_MINUTES)

    async def _build_seat_entry(self, session, seat) -> dict:
        """Build one seat dict.

        Phase 19 contributions:
        - Alias fields ``seat_role`` and ``occupant_type`` (so downstream code
          that prefers the explicit names works).
        - ``persona`` payload from the Seat row (if column exists).
        - ``display_name`` resolved via :func:`_resolve_ai_display_name`.
        """
        entry: dict[str, Any] = {
            "role": seat.seat_role,
            "seat_role": seat.seat_role,
            "type": seat.occupant_type,
            "occupant_type": seat.occupant_type,
        }
        if seat.agent_id:
            entry["agent_id"] = seat.agent_id

        # Phase 19 — persona snapshot (column may not exist pre-19)
        persona_payload = getattr(seat, "persona", None)
        if persona_payload:
            entry["persona"] = persona_payload

        if seat.occupant_type == "ai" and seat.seat_role:
            entry["display_name"] = self._resolve_ai_display_name(
                seat.seat_role, persona_payload
            )
        elif seat.occupant_type == "human" and seat.user_id:
            from app.db.models.user import User
            u_row = await session.execute(select(User).where(User.id == seat.user_id))
            u = u_row.scalar_one_or_none()
            if u:
                entry["user_name"] = u.display_name

        return entry

    async def _load_canvas_perception(self, micro_phase: str | None = None) -> dict:
        try:
            from app.canvas.tools_perception import get_canvas_snapshot
            snapshot = await get_canvas_snapshot(self._project_id)
            return _normalize_canvas(snapshot, micro_phase)
        except Exception as exc:
            logger.debug("Spatial perception failed, falling back to legacy: %s", exc)

        try:
            from app.bridge.canvas_ops import canvas_ops
            return await canvas_ops.get_canvas_state(self._project_id)
        except Exception as exc:
            logger.warning("Failed to load canvas from sidecar: %s", exc)
            return {"total_notes": 0, "groups": [], "ungrouped": [], "notes": []}

    # -------- Chat / actions --------

    async def _load_chat(self, r: aioredis.Redis) -> list[dict]:
        """Load recent chat messages.

        Phase 20 contribution: the DB fallback path applies ``group_only_filter()``
        so personal (DT-coach) messages never leak into agent context.

        The Redis cache layer is unchanged — Phase 20 ensures personal events
        are simply never pushed to ``project:*:chat_events`` upstream
        (see ``app.ws.chat_ws`` Phase 20 changes).
        """
        from app.db.models.message import Message

        key = _KEY_CHAT.format(project_id=self._project_id)
        raw_list = await r.lrange(key, 0, -1)
        if raw_list:
            result: list[dict] = []
            for raw in raw_list:
                try:
                    result.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
            return result

        async with async_session_factory() as session:
            query = select(Message).where(Message.project_id == self._project_id)

            # Phase 20 — spec §9.1: agent context must never expose personal chat.
            try:
                from app.chat.message_filters import group_only_filter
                query = query.where(group_only_filter())
            except ImportError:
                pass  # Pre-Phase-20 — Message has no chat_id column yet.

            rows = await session.execute(
                query.order_by(Message.created_at.desc(), Message.id.desc()).limit(_CHAT_LIMIT)
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
        result: list[dict] = []
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
