"""Tests for tool_create_note's gate integration (Spec 13, Step 17.4).

Verifies the gate-evaluation logic: zone resolution, color check, content gate,
and template validation against the AI / human / force_publish matrix.
"""

from __future__ import annotations

import pytest

from app.canvas.tools_manipulation import (
    CreateNoteOutcome,
    GateRejection,
    _evaluate_create_gates,
)


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _mock_redis_zone_registry(monkeypatch):
    """Avoid Redis calls; gate evaluation falls back to zone default bounds."""
    async def _empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(
        "app.canvas.tools_manipulation.get_all_zones_for_project",
        _empty,
    )


class TestZoneResolution:
    async def test_no_active_zone_at_coord(self) -> None:
        # Far outside any default bounds
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="x",
            color="yellow",
            x=999999,
            y=999999,
            sub_phase_id="2.2",
            author_type="ai",
            force_publish=False,
        )
        assert outcome.rejection is not None
        assert outcome.rejection.rule_module == "zone_resolution"

    async def test_no_sub_phase_skips_gates(self) -> None:
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="anything",
            color="yellow",
            x=100,
            y=100,
            sub_phase_id=None,
            author_type="ai",
            force_publish=False,
        )
        assert outcome.rejection is None
        assert outcome.success is True


class TestColorCheck:
    async def test_disallowed_color_not_enforced(self) -> None:
        """作者身分色永遠勝出：色不合 zone 不再 reject / coerce。

        每個角色一個固定專屬色，便條色由作者席位色決定，與 zone allowed_colors 無關。
        即使便條因 template 等其他規則被擋，「顏色」永遠不是拒絕原因。
        """
        # define_criteria_sidebar 僅允許 green；這裡用 yellow。
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="準則：時間",
            color="yellow",
            x=200,
            y=5800,  # inside criteria band default bounds（RC1 帶模型）
            sub_phase_id="2.5",
            author_type="ai",
            force_publish=False,
        )
        # 顏色不合不再產生 zone_color 拒絕（可能因其他 gate 被擋，但原因絕非顏色）。
        assert outcome.rejection is None or outcome.rejection.rule_module != "zone_color"


class TestContentGate:
    async def test_no_solution_language_blocked_for_ai(self) -> None:
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="做一個運費 widget",
            color="yellow",
            x=200,
            y=3800,
            sub_phase_id="2.2",
            author_type="ai",
            force_publish=False,
        )
        assert outcome.rejection is not None
        assert outcome.rejection.rule_module == "no_solution_language"
        assert outcome.gate_violation_metadata is None  # AI hard reject

    async def test_human_force_publish_creates_violation_metadata(self) -> None:
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="做一個運費 widget",
            color="yellow",
            x=200,
            y=3800,
            sub_phase_id="2.2",
            author_type="human",
            force_publish=True,
        )
        # Rejection still set, but metadata indicates override
        assert outcome.rejection is not None
        assert outcome.gate_violation_metadata is not None
        assert outcome.gate_violation_metadata["module"] == "no_solution_language"

    async def test_human_no_force_still_hard_reject(self) -> None:
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="做一個",
            color="yellow",
            x=200,
            y=3800,
            sub_phase_id="2.2",
            author_type="human",
            force_publish=False,
        )
        assert outcome.rejection is not None
        assert outcome.gate_violation_metadata is None


# Phase 42 C1：TestRawWallNoInterpretation 刪除——鎖死已移除行為（1.5 Raw Wall 與
# no_interpretation gate 隨 5+7 重構全系統移除，spec 04-06 v4.25 §5.5）。
# 註：該 class 的 test_blocked 在移除前已是 pre-existing fail（2026-06-03 口徑）。


class TestParkRemoved:
    """Phase 21：Park（孤兒區）概念已移除。原本落在 park 區域座標的便條，
    現在會被視為「不在任何 active zone」而 reject。"""

    async def test_old_park_coords_now_rejected(self) -> None:
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="做一個解法",
            color="yellow",
            x=2450,
            y=100,
            sub_phase_id="2.2",
            author_type="ai",
            force_publish=False,
        )
        assert outcome.success is False
        assert outcome.rejection is not None
