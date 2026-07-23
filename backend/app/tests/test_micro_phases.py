"""Unit tests for app.stages.micro_phases state machine.

Phase 42 C1（spec 22 v2.0 §2.3a/§2.4、04-06 v4.25 §4.1）：micro 重寫為 6 桶
{0.0, 1.1, 1.2, 2.1, 2.2, 2.3}；0.1/0.2/1.3 正式移除。
"""
from __future__ import annotations

import pytest

from app.stages.micro_phases import (
    MICRO_PHASES,
    MICRO_PHASE_ORDER,
    _STAGE_TO_FIRST_MICRO,
    get_first_micro_phase_for_stage,
    get_macro_stage,
    get_next_micro_phase,
    get_role_status,
    is_backtrack,
    is_macro_boundary,
    validate_advance,
    validate_backtrack,
)

# ---------------------------------------------------------------------------
# 1. 新 6 桶（spec 22 v2.0 §10.2）
# ---------------------------------------------------------------------------

EXPECTED_PHASES = ["0.0", "1.1", "1.2", "2.1", "2.2", "2.3"]


def test_all_phases_in_micro_phases_dict() -> None:
    assert set(EXPECTED_PHASES) == set(MICRO_PHASES.keys())


def test_micro_phase_order_matches_spec() -> None:
    # spec 22 v2.0 §10.2
    assert MICRO_PHASE_ORDER == ("0.0", "1.1", "1.2", "2.1", "2.2", "2.3")


def test_removed_micros_absent() -> None:
    # spec 22 v2.0 §10.3：micro 0.1/0.2/1.3 不在 MICRO_PHASES／MICRO_PHASE_ORDER。
    for phase_id in ("0.1", "0.2", "1.3"):
        assert phase_id not in MICRO_PHASES
        assert phase_id not in MICRO_PHASE_ORDER


def test_no_develop_deliver_phases() -> None:
    """Phase 29: regress that 3.x / 4.x are not re-introduced."""
    for phase_id in ("3.1", "3.2", "3.3", "4.1", "4.2", "4.3"):
        assert phase_id not in MICRO_PHASES
        assert phase_id not in MICRO_PHASE_ORDER


def test_name_zh_in_scene() -> None:
    # spec 22 v2.0 §2.3a：大白話、去講義標籤、無英文縮寫。
    expected = {
        "0.0": "破冰時間",
        "1.1": "經驗分享與利害關係人",
        "1.2": "發想痛點與情境",
        "2.1": "痛點歸類",
        "2.2": "問題定義與深掘",
        "2.3": "訂準則、收斂與設計題目",
    }
    for phase_id, name in expected.items():
        assert MICRO_PHASES[phase_id].name_zh == name, phase_id
    for mp in MICRO_PHASES.values():
        assert "講義" not in mp.name_zh
        for banned in ("HMW", "POV", "Persona"):
            assert banned not in mp.name_zh, f"{mp.id} name_zh 含 {banned}"


def test_name_en_suggested_values() -> None:
    # spec 22 v2.0 §2.3a name_en 建議值。
    assert MICRO_PHASES["0.0"].name_en == "warmup-icebreaker"
    assert MICRO_PHASES["1.1"].name_en == "experience-sharing-and-stakeholders"
    assert MICRO_PHASES["1.2"].name_en == "pain-point-ideation"
    assert MICRO_PHASES["2.1"].name_en == "pain-point-clustering"
    assert MICRO_PHASES["2.2"].name_en == "problem-definition-and-deepening"
    assert MICRO_PHASES["2.3"].name_en == "criteria-convergence-and-design-question"


# ---------------------------------------------------------------------------
# 2. macro_stage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase_id,expected_macro", [
    ("0.0", "warmup"),
    ("1.1", "discover"), ("1.2", "discover"),
    ("2.1", "define"), ("2.2", "define"), ("2.3", "define"),
])
def test_macro_stage_field(phase_id: str, expected_macro: str) -> None:
    assert MICRO_PHASES[phase_id].macro_stage == expected_macro
    assert get_macro_stage(phase_id) == expected_macro


def test_stage_to_first_micro() -> None:
    # spec 22 v2.0 §10.2：warmup→0.0、discover→1.1、define→2.1。
    assert _STAGE_TO_FIRST_MICRO == {
        "warmup": "0.0", "discover": "1.1", "define": "2.1"
    }
    assert get_first_micro_phase_for_stage("discover") == "1.1"
    assert get_first_micro_phase_for_stage("completed") is None


# ---------------------------------------------------------------------------
# 3. get_next_micro_phase()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("current,expected_next", [
    ("0.0", "1.1"),
    ("1.1", "1.2"), ("1.2", "2.1"),
    ("2.1", "2.2"), ("2.2", "2.3"),
])
def test_get_next_micro_phase_transitions(current: str, expected_next: str) -> None:
    assert get_next_micro_phase(current) == expected_next


def test_get_next_micro_phase_end_returns_none() -> None:
    """2.3 is the terminal micro-phase（define→completed）。"""
    assert get_next_micro_phase("2.3") is None


def test_get_next_micro_phase_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_next_micro_phase("9.9")
    with pytest.raises(KeyError):
        get_next_micro_phase("1.3")  # 移除桶＝未知 id


# ---------------------------------------------------------------------------
# 4. validate_advance()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_id,to_id", [
    ("0.0", "1.1"),
    ("1.1", "1.2"), ("1.2", "2.1"),
    ("2.1", "2.2"), ("2.2", "2.3"),
])
def test_validate_advance_accepts_next(from_id: str, to_id: str) -> None:
    assert validate_advance(from_id, to_id) is True


@pytest.mark.parametrize("from_id,to_id", [
    ("1.1", "2.1"),  # skip one
    ("0.0", "1.2"),  # skip into mid-discover
    ("2.1", "2.3"),  # skip two within macro
])
def test_validate_advance_rejects_skipping(from_id: str, to_id: str) -> None:
    assert validate_advance(from_id, to_id) is False


# ---------------------------------------------------------------------------
# 5. validate_backtrack() and is_backtrack()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_id,to_id", [
    ("1.2", "1.1"),
    ("2.1", "1.2"),
    ("2.3", "1.1"),
])
def test_validate_backtrack_accepts_backward(from_id: str, to_id: str) -> None:
    assert validate_backtrack(from_id, to_id) is True


@pytest.mark.parametrize("from_id,to_id", [
    ("1.1", "1.2"),
    ("2.1", "2.2"),
    ("1.2", "2.1"),
])
def test_validate_backtrack_rejects_forward(from_id: str, to_id: str) -> None:
    assert validate_backtrack(from_id, to_id) is False


@pytest.mark.parametrize("from_id,to_id,expected", [
    ("1.2", "1.1", True),
    ("2.1", "1.2", True),
    ("1.1", "1.2", False),
    ("2.1", "2.2", False),
])
def test_is_backtrack(from_id: str, to_id: str, expected: bool) -> None:
    assert is_backtrack(from_id, to_id) is expected


# ---------------------------------------------------------------------------
# 6. get_role_status()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase_id,role,expected_status", [
    # 1.1：crew_1=protagonist (empathy)，crew_2/crew_4=suppressed（structure/feasibility）
    ("1.1", "crew_1", "protagonist"),
    ("1.1", "crew_2", "suppressed"),
    ("1.1", "crew_4", "suppressed"),
    ("1.1", "crew_3", "normal"),
    # 1.2（發想痛點）：empathy 主導、feasibility 收手
    ("1.2", "crew_1", "protagonist"),
    ("1.2", "crew_4", "suppressed"),
    # 2.1 / 2.2：crew_2 (structure) is protagonist
    ("2.1", "crew_2", "protagonist"),
    ("2.2", "crew_2", "protagonist"),
])
def test_get_role_status_role_dynamics(phase_id: str, role: str, expected_status: str) -> None:
    assert get_role_status(phase_id, role) == expected_status


@pytest.mark.parametrize("phase_id", EXPECTED_PHASES)
def test_supervisor_always_normal(phase_id: str) -> None:
    assert get_role_status(phase_id, "supervisor") == "normal"


# ---------------------------------------------------------------------------
# 7. is_macro_boundary()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_id,to_id,expected", [
    ("0.0", "1.1", True),   # warmup → discover
    ("1.2", "2.1", True),   # discover → define（新邊界＝1.2 完成）
    ("1.1", "1.2", False),
    ("2.1", "2.2", False),
])
def test_is_macro_boundary(from_id: str, to_id: str, expected: bool) -> None:
    assert is_macro_boundary(from_id, to_id) is expected
