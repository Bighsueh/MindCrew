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
    async def test_disallowed_color_rejected(self) -> None:
        # define_criteria_sidebar only allows green; try yellow
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="準則：時間",
            color="yellow",
            x=2160,
            y=200,  # inside criteria sidebar default bounds
            sub_phase_id="2.5",
            author_type="ai",
            force_publish=False,
        )
        assert outcome.rejection is not None
        assert outcome.rejection.rule_module == "zone_color"


class TestContentGate:
    async def test_no_solution_language_blocked_for_ai(self) -> None:
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="做一個運費 widget",
            color="yellow",
            x=200,
            y=200,
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
            y=200,
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
            y=200,
            sub_phase_id="2.2",
            author_type="human",
            force_publish=False,
        )
        assert outcome.rejection is not None
        assert outcome.gate_violation_metadata is None


class TestRawWallNoInterpretation:
    async def test_blocked(self) -> None:
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text='使用者真正的需求是更快結帳',
            color="yellow",
            x=200,
            y=200,
            sub_phase_id="1.5",
            author_type="ai",
            force_publish=False,
        )
        assert outcome.rejection is not None
        assert outcome.rejection.rule_module == "no_interpretation"

    async def test_passes(self) -> None:
        # Pass valid raw observation matching template
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text='"我都搞不清楚要按哪裡"｜情緒：焦躁｜來源：U2',
            color="yellow",
            x=200,
            y=200,
            sub_phase_id="1.5",
            author_type="ai",
            force_publish=False,
        )
        assert outcome.rejection is None
        assert outcome.success is True


class TestParkBypassesContentGate:
    async def test_park_allows_anything(self) -> None:
        # Park bounds = x=2400..2640
        outcome = await _evaluate_create_gates(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            text="做一個解法（測試 park 不擋）",
            color="yellow",
            x=2450,
            y=100,
            sub_phase_id="2.2",  # solution-language phase
            author_type="ai",
            force_publish=False,
        )
        assert outcome.success is True
        assert outcome.zone_id == "park"
