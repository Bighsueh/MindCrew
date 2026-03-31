"""Unit tests for app.stages.micro_phases state machine (Phase 12.2)."""
from __future__ import annotations

import pytest

from app.stages.micro_phases import (
    MICRO_PHASES,
    MICRO_PHASE_ORDER,
    get_macro_stage,
    get_next_micro_phase,
    get_role_status,
    is_backtrack,
    is_macro_boundary,
    validate_advance,
    validate_backtrack,
)

# ---------------------------------------------------------------------------
# 1. All 12 phases present
# ---------------------------------------------------------------------------

EXPECTED_PHASES = [
    "1.1", "1.2", "1.3",
    "2.1", "2.2", "2.3",
    "3.1", "3.2", "3.3",
    "4.1", "4.2", "4.3",
]


def test_all_phases_in_micro_phases_dict() -> None:
    assert set(EXPECTED_PHASES) == set(MICRO_PHASES.keys())


def test_all_phases_in_micro_phase_order() -> None:
    assert list(EXPECTED_PHASES) == list(MICRO_PHASE_ORDER)


# ---------------------------------------------------------------------------
# 2. Valid macro_stage for every phase
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase_id,expected_macro", [
    ("1.1", "discover"), ("1.2", "discover"), ("1.3", "discover"),
    ("2.1", "define"),   ("2.2", "define"),   ("2.3", "define"),
    ("3.1", "develop"),  ("3.2", "develop"),  ("3.3", "develop"),
    ("4.1", "deliver"),  ("4.2", "deliver"),  ("4.3", "deliver"),
])
def test_macro_stage_field(phase_id: str, expected_macro: str) -> None:
    assert MICRO_PHASES[phase_id].macro_stage == expected_macro


# ---------------------------------------------------------------------------
# 3. get_macro_stage()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase_id,expected_macro", [
    ("1.1", "discover"), ("1.2", "discover"), ("1.3", "discover"),
    ("2.1", "define"),   ("2.2", "define"),   ("2.3", "define"),
    ("3.1", "develop"),  ("3.2", "develop"),  ("3.3", "develop"),
    ("4.1", "deliver"),  ("4.2", "deliver"),  ("4.3", "deliver"),
])
def test_get_macro_stage(phase_id: str, expected_macro: str) -> None:
    assert get_macro_stage(phase_id) == expected_macro


# ---------------------------------------------------------------------------
# 4. get_next_micro_phase()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("current,expected_next", [
    ("1.1", "1.2"), ("1.2", "1.3"), ("1.3", "2.1"),
    ("2.1", "2.2"), ("2.2", "2.3"), ("2.3", "3.1"),
    ("3.1", "3.2"), ("3.2", "3.3"), ("3.3", "4.1"),
    ("4.1", "4.2"), ("4.2", "4.3"),
])
def test_get_next_micro_phase_transitions(current: str, expected_next: str) -> None:
    assert get_next_micro_phase(current) == expected_next


def test_get_next_micro_phase_end_returns_none() -> None:
    assert get_next_micro_phase("4.3") is None


def test_get_next_micro_phase_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_next_micro_phase("9.9")


# ---------------------------------------------------------------------------
# 5. validate_advance()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_id,to_id", [
    ("1.1", "1.2"), ("1.2", "1.3"), ("1.3", "2.1"),
    ("2.1", "2.2"), ("2.2", "2.3"), ("2.3", "3.1"),
    ("3.1", "3.2"), ("3.2", "3.3"), ("3.3", "4.1"),
    ("4.1", "4.2"), ("4.2", "4.3"),
])
def test_validate_advance_accepts_next(from_id: str, to_id: str) -> None:
    assert validate_advance(from_id, to_id) is True


@pytest.mark.parametrize("from_id,to_id", [
    ("1.1", "1.3"),  # skip one
    ("1.1", "2.1"),  # skip entire macro stage
    ("2.1", "3.1"),  # skip two
    ("3.1", "4.1"),  # skip across boundary
])
def test_validate_advance_rejects_skipping(from_id: str, to_id: str) -> None:
    assert validate_advance(from_id, to_id) is False


# ---------------------------------------------------------------------------
# 6. validate_backtrack() and is_backtrack()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_id,to_id", [
    ("1.2", "1.1"),
    ("2.1", "1.3"),
    ("3.1", "2.1"),
    ("4.3", "3.1"),
    ("4.3", "4.1"),
    ("3.2", "1.3"),
])
def test_validate_backtrack_accepts_backward(from_id: str, to_id: str) -> None:
    assert validate_backtrack(from_id, to_id) is True


@pytest.mark.parametrize("from_id,to_id", [
    ("1.1", "1.2"),
    ("2.1", "3.1"),
    ("1.3", "2.1"),
])
def test_validate_backtrack_rejects_forward(from_id: str, to_id: str) -> None:
    assert validate_backtrack(from_id, to_id) is False


@pytest.mark.parametrize("from_id,to_id,expected", [
    ("1.2", "1.1", True),
    ("3.1", "2.1", True),
    ("1.1", "1.2", False),
    ("2.1", "3.1", False),
])
def test_is_backtrack(from_id: str, to_id: str, expected: bool) -> None:
    assert is_backtrack(from_id, to_id) is expected


# ---------------------------------------------------------------------------
# 7. get_role_status()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase_id,role,expected_status", [
    # Phase 1.1: crew_1=protagonist, crew_2/crew_4=suppressed, crew_3=normal
    ("1.1", "crew_1", "protagonist"),
    ("1.1", "crew_2", "suppressed"),
    ("1.1", "crew_4", "suppressed"),
    ("1.1", "crew_3", "normal"),
    # Phase 3.1: crew_3=protagonist, crew_2/crew_4=suppressed
    ("3.1", "crew_3", "protagonist"),
    ("3.1", "crew_2", "suppressed"),
    ("3.1", "crew_4", "suppressed"),
    # Phase 3.2: crew_2=protagonist, crew_1/crew_3/crew_4=suppressed
    ("3.2", "crew_2", "protagonist"),
    ("3.2", "crew_1", "suppressed"),
    ("3.2", "crew_3", "suppressed"),
    ("3.2", "crew_4", "suppressed"),
])
def test_get_role_status_role_dynamics(phase_id: str, role: str, expected_status: str) -> None:
    assert get_role_status(phase_id, role) == expected_status


@pytest.mark.parametrize("phase_id", EXPECTED_PHASES)
def test_supervisor_always_normal(phase_id: str) -> None:
    assert get_role_status(phase_id, "supervisor") == "normal"


# ---------------------------------------------------------------------------
# 8. is_macro_boundary()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_id,to_id,expected", [
    ("1.3", "2.1", True),
    ("2.3", "3.1", True),
    ("3.3", "4.1", True),
    ("1.1", "1.2", False),
    ("2.1", "2.2", False),
    ("3.1", "3.2", False),
    ("4.1", "4.2", False),
])
def test_is_macro_boundary(from_id: str, to_id: str, expected: bool) -> None:
    assert is_macro_boundary(from_id, to_id) is expected
