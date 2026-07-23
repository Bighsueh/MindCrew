"""Micro-phase definitions and state-machine helpers.

Phase 19 refactor: Each micro-phase declares a ``needed_lens`` and a set of
``suppressed_lenses``. Concrete seat assignment is resolved at runtime by
:func:`app.agents.personas.resolver.resolve_protagonist_seat` against the
project's actual personas. This decouples DT phase strategy from the
legacy ``crew_1=empathy`` hardcoding.

System scope: first diamond only (warmup → discover → define → completed).

Backward compatibility:
- ``get_role_status`` accepts an optional ``seats`` list. When omitted,
  it falls back to the legacy 4-capability personas so existing call
  sites and tests continue to work without modification.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.agents.personas.lens import CognitiveLens
from app.agents.personas.models import build_fallback_personas
from app.agents.personas.resolver import (
    resolve_protagonist_seat,
    resolve_suppressed_seats,
)


@dataclass(frozen=True)
class MicroPhase:
    """A single Design Thinking micro-phase.

    Attributes:
        id: e.g. "1.1"
        macro_stage: warmup | discover | define
        name_zh / name_en: human-readable labels
        needed_lens: the cognitive lens that should lead this phase (or None)
        suppressed_lenses: lenses that should be muted this phase
    """

    id: str
    macro_stage: str  # warmup | discover | define
    name_zh: str
    name_en: str
    needed_lens: CognitiveLens | None
    suppressed_lenses: tuple[CognitiveLens, ...]


# Phase 42 C1 (spec/22 v2.0 §2.3a)：micro 重寫為 6 桶
# {0.0, 1.1, 1.2, 2.1, 2.2=2.2–2.4, 2.3=2.5–2.7}；0.1/0.2/1.3 正式移除。
# name_zh＝in-scene 大白話（講義溯源標籤降到 spec 22 §2.1，#25）。
# needed_lens/suppressed_lenses 為 spec 未規範項：id 沿用者保留既有配置、
# 新 1.2（發想痛點）沿用舊發散期配置（EMPATHY 視角主導替各群代言、結構收手），記錄為 C1 裁定。
MICRO_PHASES: dict[str, MicroPhase] = {
    # 暖場 macro stage（第一級階段）：目標導向破冰。專案入口。
    "0.0": MicroPhase(
        id="0.0",
        macro_stage="warmup",
        name_zh="破冰時間",
        name_en="warmup-icebreaker",
        needed_lens=None,
        suppressed_lenses=(),
    ),
    "1.1": MicroPhase(
        id="1.1",
        macro_stage="discover",
        name_zh="經驗分享與利害關係人",
        name_en="experience-sharing-and-stakeholders",
        needed_lens=CognitiveLens.EMPATHY,
        suppressed_lenses=(CognitiveLens.STRUCTURE, CognitiveLens.FEASIBILITY),
    ),
    "1.2": MicroPhase(
        id="1.2",
        macro_stage="discover",
        name_zh="發想痛點與情境",
        name_en="pain-point-ideation",
        needed_lens=CognitiveLens.EMPATHY,
        suppressed_lenses=(CognitiveLens.FEASIBILITY,),
    ),
    "2.1": MicroPhase(
        id="2.1",
        macro_stage="define",
        name_zh="痛點歸類",
        name_en="pain-point-clustering",
        needed_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=(),
    ),
    "2.2": MicroPhase(
        id="2.2",
        macro_stage="define",
        name_zh="問題定義與深掘",
        name_en="problem-definition-and-deepening",
        needed_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=(),
    ),
    "2.3": MicroPhase(
        id="2.3",
        macro_stage="define",
        name_zh="訂準則、收斂與設計題目",
        name_en="criteria-convergence-and-design-question",
        needed_lens=None,
        suppressed_lenses=(),
    ),
}

# Phase 42 C1 (spec/22 v2.0 §2.4)：6 個 micro 桶。
# 2.3 推進不再進入 3.1，改觸發 FirstDiamondCompletedEvent（見 stage_advancement.py）。
MICRO_PHASE_ORDER: tuple[str, ...] = (
    "0.0",            # 暖場（warmup macro stage）
    "1.1", "1.2",     # 發現階段
    "2.1", "2.2", "2.3",  # 定義階段
)


def get_micro_phase(phase_id: str) -> MicroPhase:
    """Get MicroPhase by ID. Raises KeyError if not found."""
    return MICRO_PHASES[phase_id]


def get_macro_stage(phase_id: str) -> str:
    """Map micro phase ID to macro stage. '1.2' -> 'discover'"""
    return MICRO_PHASES[phase_id].macro_stage


def get_next_micro_phase(current: str) -> str | None:
    """Get the next phase in sequence. Returns None at the end of 2.3."""
    try:
        idx = MICRO_PHASE_ORDER.index(current)
    except ValueError as exc:
        raise KeyError(f"Unknown phase id: {current!r}") from exc

    next_idx = idx + 1
    if next_idx >= len(MICRO_PHASE_ORDER):
        return None
    return MICRO_PHASE_ORDER[next_idx]


def validate_advance(from_id: str, to_id: str) -> bool:
    """Validate forward advancement. Only allows next-in-sequence."""
    return get_next_micro_phase(from_id) == to_id


def validate_backtrack(from_id: str, to_id: str) -> bool:
    """Validate backtrack.

    For simplicity: allow any backward move (to_id < from_id in MICRO_PHASE_ORDER).
    """
    return is_backtrack(from_id, to_id)


def is_backtrack(from_id: str, to_id: str) -> bool:
    """True if to_id comes before from_id in the sequence."""
    try:
        from_idx = MICRO_PHASE_ORDER.index(from_id)
        to_idx = MICRO_PHASE_ORDER.index(to_id)
    except ValueError:
        return False
    return to_idx < from_idx


# ---------------------------------------------------------------------------
# Role-status resolution (lens-based)
# ---------------------------------------------------------------------------

def _legacy_fallback_seats() -> list[dict[str, Any]]:
    """Build legacy seats from fallback personas (crew_1..crew_4)."""
    fallbacks = build_fallback_personas()
    seats: list[dict[str, Any]] = [
        {"seat_role": "supervisor", "occupant_type": "ai", "persona": None}
    ]
    for seat_role, persona in fallbacks.items():
        from app.agents.personas.models import persona_to_dict
        seats.append(
            {
                "seat_role": seat_role,
                "occupant_type": "ai",
                "persona": persona_to_dict(persona) if persona else None,
            }
        )
    return seats


def get_role_status(
    phase_id: str,
    seat_role: str,
    seats: Iterable[Any] | None = None,
) -> str:
    """Return 'protagonist', 'suppressed', or 'normal' for a seat in a phase.

    Supervisor is always 'normal' (supervisor has its own behaviour rules).

    Args:
        phase_id: micro-phase id (e.g. "1.1")
        seat_role: seat to evaluate (e.g. "crew_2")
        seats: project seats with personas. If omitted, falls back to legacy
            crew_1..crew_4 capability personas (used by tests and code paths
            that pre-date Phase 19).
    """
    phase = MICRO_PHASES[phase_id]
    if seat_role == "supervisor":
        return "normal"
    resolved_seats = list(seats) if seats is not None else _legacy_fallback_seats()
    protagonist_role = resolve_protagonist_seat(resolved_seats, phase.needed_lens)
    if protagonist_role == seat_role:
        return "protagonist"
    suppressed = resolve_suppressed_seats(
        resolved_seats,
        phase.suppressed_lenses,
        protect_seat=protagonist_role,
    )
    if seat_role in suppressed:
        return "suppressed"
    return "normal"


def is_macro_boundary(from_id: str, to_id: str) -> bool:
    """True if the transition crosses macro phase boundaries."""
    return get_macro_stage(from_id) != get_macro_stage(to_id)


# Mapping from macro stage to first micro phase
# 'completed' is a terminal stage without a micro phase.
# Phase 42 C1 (spec/22 §2.4)：warmup→0.0、discover→1.1（0.1 移除後不再經 Phase 0）、define→2.1。
_STAGE_TO_FIRST_MICRO: dict[str, str] = {
    "warmup": "0.0",
    "discover": "1.1",
    "define": "2.1",
}


def get_first_micro_phase_for_stage(stage: str) -> str | None:
    """Get the first micro phase ID for a given macro stage."""
    return _STAGE_TO_FIRST_MICRO.get(stage)
