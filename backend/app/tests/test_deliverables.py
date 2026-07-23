"""Tests for sub_phase deliverable check（Phase 18 A9 機制；Phase 42 C1 配置歸零）.

spec 25 v2.0 §2.4：v2.0 配置現況「多為空」——舊 1.1d scope_rationale 與 2.7 藍色
便條 deliverable 隨新 5＋7 格移除（#34 便條色＝作者色）；``check_deliverables``
**機制保留**供未來使用，空配置一律放行。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.stages.deliverables import check_deliverables
from app.stages.sub_phases import SUB_PHASE_ORDER, SUB_PHASES

pytestmark = pytest.mark.asyncio


@dataclass
class FakeNote:
    id: str
    x: float
    y: float
    color: str = "yellow"
    content: str = ""


@dataclass
class FakeClusterState:
    clusters: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.clusters is None:
            self.clusters = []


@dataclass
class FakeAnalysis:
    notes: list
    cluster_state: FakeClusterState


class FakeAnalyzer:
    def __init__(self, notes):
        self.notes = notes

    async def analyze(self, project_id):
        return FakeAnalysis(notes=self.notes, cluster_state=FakeClusterState())


@pytest.fixture(autouse=True)
def _mock_zone_registry(monkeypatch):
    async def empty(*a, **kw): return {}
    monkeypatch.setattr(
        "app.stages.deliverables.get_all_zones_for_project",
        empty,
    )


def _patch_analyzer(monkeypatch, notes):
    fake = FakeAnalyzer(notes)
    monkeypatch.setattr(
        "app.canvas.analyzer.get_spatial_analyzer",
        lambda: fake,
    )


class TestEmptyConfigPasses:
    async def test_all_cells_pass_with_empty_canvas(self, monkeypatch) -> None:
        # v2.0 配置全空 → 任何格的 deliverable check 都放行（張數/配對由
        # artifact gate 管、真人參與由 round_lock 管，spec 25 §2.4 三層分工）。
        _patch_analyzer(monkeypatch, [])
        for sub_id in SUB_PHASE_ORDER:
            result = await check_deliverables(
                "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
                sub_id,
            )
            assert result.passed is True, sub_id
            assert result.missing == []


class TestRegistryDeliverablesEmpty:
    def test_old_deliverables_removed(self) -> None:
        # Phase 42 C1：舊 1.1d scope_rationale 與 2.7 blue HMW deliverable 移除。
        for sub_id, sp in SUB_PHASES.items():
            assert sp.deliverables_required == (), (
                f"{sub_id} 不應再有 deliverables_required（v2.0 配置歸零）"
            )
