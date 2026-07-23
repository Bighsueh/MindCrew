"""Phase 29 (2026-05-26): regression tests for first-diamond-only scope.

依據 spec/01-PRD.md §10, spec/04-06-micro-phase-state.md §4.10。

These tests pin down the contract after develop / deliver removal:
- ``get_next_stage`` returns ``"completed"`` from ``"define"``, ``None`` from ``"completed"``.
- ``advance_stage`` emits ``FirstDiamondCompletedEvent`` when reaching terminal.
- ``MICRO_PHASES`` / ``SUB_PHASES`` / ``ZONES`` no longer contain 3.x / 4.x ids.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.stage_advancement import advance_stage, get_next_stage
from app.canvas.zones import ZONES
from app.events.types import FirstDiamondCompletedEvent
from app.stages.micro_phases import MICRO_PHASES, MICRO_PHASE_ORDER
from app.stages.sub_phases import SUB_PHASE_ORDER

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Registry contract: no develop / deliver
# ---------------------------------------------------------------------------


class TestRegistries:
    def test_micro_phases_only_first_diamond(self) -> None:
        # Phase 42 C1（spec 22 v2.0 §2.3a）：6 桶；0.1/0.2/1.3 移除。
        assert set(MICRO_PHASES.keys()) == {
            "0.0",
            "1.1", "1.2",
            "2.1", "2.2", "2.3",
        }

    def test_micro_phase_order_only_first_diamond(self) -> None:
        for phase_id in MICRO_PHASE_ORDER:
            assert not phase_id.startswith(("3.", "4.")), (
                f"unexpected micro_phase {phase_id}"
            )

    def test_sub_phase_order_only_first_diamond(self) -> None:
        for sub_id in SUB_PHASE_ORDER:
            assert not sub_id.startswith(("3.", "4.")), (
                f"unexpected sub_phase {sub_id}"
            )

    def test_zones_no_second_diamond(self) -> None:
        for removed in (
            "idea_pool", "deliver_criteria_sidebar", "hypothesis_wall",
            "task_area", "prototype_zone", "direction_zone",
            "debrief_q1", "debrief_q2", "debrief_q3",
        ):
            assert removed not in ZONES, f"{removed} zone should be removed"


# ---------------------------------------------------------------------------
# Stage progression: define → completed (terminal)
# ---------------------------------------------------------------------------


class TestStageProgression:
    def test_get_next_stage_discover_to_define(self) -> None:
        assert get_next_stage("discover") == "define"

    def test_get_next_stage_define_to_completed(self) -> None:
        """Phase 29: define no longer advances to develop."""
        assert get_next_stage("define") == "completed"

    def test_get_next_stage_completed_returns_none(self) -> None:
        assert get_next_stage("completed") is None

    def test_get_next_stage_unknown_returns_none(self) -> None:
        assert get_next_stage("nonsense") is None

    def test_no_develop_in_progression(self) -> None:
        """Regression: develop must not appear as a next stage."""
        for stage in ("discover", "define", "completed"):
            nxt = get_next_stage(stage)
            assert nxt != "develop"
            assert nxt != "deliver"


# ---------------------------------------------------------------------------
# advance_stage emits FirstDiamondCompletedEvent on terminal
# ---------------------------------------------------------------------------


class TestFirstDiamondTerminalEvent:
    async def test_advance_from_define_emits_first_diamond_completed_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When define advances to completed, FirstDiamondCompletedEvent must fire."""
        published_events: list = []

        async def fake_publish(event):
            published_events.append(event)

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=fake_publish)

        # Patch async_session_factory + canvas snapshot + event_bus + TimerService
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        class _SessionCM:
            async def __aenter__(self_inner):
                return mock_session

            async def __aexit__(self_inner, *a):
                return False

        with patch(
            "app.agents.stage_advancement.async_session_factory",
            lambda: _SessionCM(),
        ), patch(
            "app.events.bus.event_bus",
            mock_bus,
        ), patch(
            "app.canvas.tools_perception.get_canvas_snapshot",
            AsyncMock(return_value={"notes": []}),
        ):
            result = await advance_stage(
                current_stage="define",
                project_id=uuid4(),
                agent_id="ai_evaluator",
            )

        assert result == "advanced_to_completed"
        assert any(isinstance(e, FirstDiamondCompletedEvent) for e in published_events)
