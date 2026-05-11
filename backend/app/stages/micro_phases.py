"""Micro-phase definitions and state-machine helpers.

Phase 19 refactor: Each micro-phase declares a ``needed_lens`` and a set of
``suppressed_lenses``. Concrete seat assignment is resolved at runtime by
:func:`app.agents.personas.resolver.resolve_protagonist_seat` against the
project's actual personas. This decouples DT phase strategy from the
legacy ``crew_1=empathy`` hardcoding.

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
        macro_stage: discover | define | develop | deliver
        name_zh / name_en: human-readable labels
        needed_lens: the cognitive lens that should lead this phase (or None)
        suppressed_lenses: lenses that should be muted this phase
    """

    id: str
    macro_stage: str
    name_zh: str
    name_en: str
    needed_lens: CognitiveLens | None
    suppressed_lenses: tuple[CognitiveLens, ...]


MICRO_PHASES: dict[str, MicroPhase] = {
    "1.1": MicroPhase(
        id="1.1",
        macro_stage="discover",
        name_zh="暖場與經驗分享",
        name_en="warm-up-and-experience-sharing",
        needed_lens=CognitiveLens.EMPATHY,
        suppressed_lenses=(CognitiveLens.STRUCTURE, CognitiveLens.FEASIBILITY),
    ),
    "1.2": MicroPhase(
        id="1.2",
        macro_stage="discover",
        name_zh="視角擴展",
        name_en="perspective-expansion",
        needed_lens=None,
        suppressed_lenses=(CognitiveLens.STRUCTURE,),
    ),
    "1.3": MicroPhase(
        id="1.3",
        macro_stage="discover",
        name_zh="同理心收斂",
        name_en="empathy-convergence",
        needed_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=(),
    ),
    "2.1": MicroPhase(
        id="2.1",
        macro_stage="define",
        name_zh="使用者旅程追蹤",
        name_en="user-journey-tracking",
        needed_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=(),
    ),
    "2.2": MicroPhase(
        id="2.2",
        macro_stage="define",
        name_zh="洞察萃取與矛盾發掘",
        name_en="insight-extraction-and-tension-discovery",
        needed_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=(),
    ),
    "2.3": MicroPhase(
        id="2.3",
        macro_stage="define",
        name_zh="HMW 問題陳述",
        name_en="hmw-problem-statement",
        needed_lens=None,
        suppressed_lenses=(),
    ),
    "3.1": MicroPhase(
        id="3.1",
        macro_stage="develop",
        name_zh="規則建立與大量發散",
        name_en="rule-setting-and-mass-divergence",
        needed_lens=CognitiveLens.CREATIVITY,
        suppressed_lenses=(CognitiveLens.STRUCTURE, CognitiveLens.FEASIBILITY),
    ),
    "3.2": MicroPhase(
        id="3.2",
        macro_stage="develop",
        name_zh="概念分群與合併",
        name_en="concept-clustering-and-merging",
        needed_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=(
            CognitiveLens.EMPATHY,
            CognitiveLens.CREATIVITY,
            CognitiveLens.FEASIBILITY,
        ),
    ),
    "3.3": MicroPhase(
        id="3.3",
        macro_stage="develop",
        name_zh="評估收斂與方案選定",
        name_en="evaluation-convergence-and-solution-selection",
        needed_lens=CognitiveLens.FEASIBILITY,
        suppressed_lenses=(),
    ),
    "4.1": MicroPhase(
        id="4.1",
        macro_stage="deliver",
        name_zh="原型規劃與快速製作",
        name_en="prototype-planning-and-rapid-making",
        needed_lens=CognitiveLens.FEASIBILITY,
        suppressed_lenses=(),
    ),
    "4.2": MicroPhase(
        id="4.2",
        macro_stage="deliver",
        name_zh="測試設計",
        name_en="test-design",
        needed_lens=CognitiveLens.STRUCTURE,
        suppressed_lenses=(CognitiveLens.CREATIVITY,),
    ),
    "4.3": MicroPhase(
        id="4.3",
        macro_stage="deliver",
        name_zh="模擬測試與學習迭代",
        name_en="simulated-testing-and-learning-iteration",
        needed_lens=CognitiveLens.EMPATHY,
        suppressed_lenses=(),
    ),
}

MICRO_PHASE_ORDER: tuple[str, ...] = (
    "1.1", "1.2", "1.3",
    "2.1", "2.2", "2.3",
    "3.1", "3.2", "3.3",
    "4.1", "4.2", "4.3",
)


def get_micro_phase(phase_id: str) -> MicroPhase:
    """Get MicroPhase by ID. Raises KeyError if not found."""
    return MICRO_PHASES[phase_id]


def get_macro_stage(phase_id: str) -> str:
    """Map micro phase ID to macro stage. '1.2' -> 'discover'"""
    return MICRO_PHASES[phase_id].macro_stage


def get_next_micro_phase(current: str) -> str | None:
    """Get the next phase in sequence. Returns None for '4.3'."""
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

    Rules from spec §6.1:
    - 4.3 can backtrack to 3.1 (core assumption failed) or 4.1 (partial failure)
    - Any phase can backtrack to 1.3 (persona wrong)
    - 2.3/3.x can backtrack to 2.2 (insight insufficient)
    - Any phase stays at current (delivery not met)
    - Team request: any backward move

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
_STAGE_TO_FIRST_MICRO: dict[str, str] = {
    "discover": "1.1",
    "define": "2.1",
    "develop": "3.1",
    "deliver": "4.1",
}


def get_first_micro_phase_for_stage(stage: str) -> str | None:
    """Get the first micro phase ID for a given macro stage."""
    return _STAGE_TO_FIRST_MICRO.get(stage)
