"""Tests for sub_phase deliverable check (Phase 18 Step A9)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.stages.deliverables import check_deliverables
from app.stages.sub_phases import SUB_PHASES

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


class TestPhase1DeliverableScopeRationale:
    async def test_1_1d_blocks_when_no_scope_note(self, monkeypatch) -> None:
        _patch_analyzer(monkeypatch, [])
        result = await check_deliverables(
            "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            "1.1d",
        )
        assert result.passed is False
        assert any("Scope rationale" in m or "scope" in m.lower() for m in result.missing)

    async def test_1_1d_passes_with_valid_scope_note(self, monkeypatch) -> None:
        # Scope zone default bounds: x=100..1300 y=100..700
        note = FakeNote(
            id="n1", x=200, y=200, color="yellow",
            content="納入：高齡長者｜排除：照顧者｜理由：本次設計焦點為使用者本人",
        )
        _patch_analyzer(monkeypatch, [note])
        result = await check_deliverables(
            "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            "1.1d",
        )
        assert result.passed is True


class TestPhase2DeliverableHmw:
    async def test_2_7_blocks_when_no_hmw(self, monkeypatch) -> None:
        _patch_analyzer(monkeypatch, [])
        result = await check_deliverables(
            "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            "2.7",
        )
        assert result.passed is False
        assert any("HMW" in m for m in result.missing)

    async def test_2_7_passes_with_blue_hmw(self, monkeypatch) -> None:
        note = FakeNote(
            id="hmw-1", x=200, y=200, color="blue",
            content="我們如何讓使用者在列表頁看到運費?\nfrom: #pov-3",
        )
        _patch_analyzer(monkeypatch, [note])
        result = await check_deliverables(
            "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            "2.7",
        )
        assert result.passed is True


class TestPhase4DeliverableDebrief:
    async def test_4_2_blocks_when_only_one_question_answered(self, monkeypatch) -> None:
        # Only q1 zone has note (q1 x=100..800)
        notes = [FakeNote(id="n1", x=200, y=200, color="yellow", content="我們原以為 X")]
        _patch_analyzer(monkeypatch, notes)
        result = await check_deliverables(
            "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            "4.2",
        )
        assert result.passed is False
        # 應該 missing Q2 / Q3
        joined = " ".join(result.missing)
        assert "Q2" in joined or "Q3" in joined

    async def test_4_2_passes_when_all_three_answered(self, monkeypatch) -> None:
        # q1 x=100..800, q2 x=850..1550, q3 x=1600..2300
        notes = [
            FakeNote(id="n1", x=200, y=200, content="Q1 答案"),
            FakeNote(id="n2", x=900, y=200, content="Q2 答案"),
            FakeNote(id="n3", x=1700, y=200, content="Q3 答案"),
        ]
        _patch_analyzer(monkeypatch, notes)
        result = await check_deliverables(
            "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            "4.2",
        )
        assert result.passed is True


class TestNoDeliverableConstraintSubPhases:
    async def test_passes_when_no_requirements(self, monkeypatch) -> None:
        # 1.1a 沒有 deliverables_required
        _patch_analyzer(monkeypatch, [])
        result = await check_deliverables(
            "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            "1.1a",
        )
        assert result.passed is True
        assert result.missing == []


class TestRegistryHasDeliverables:
    def test_critical_sub_phases_have_deliverables(self) -> None:
        # Spec 14 A2/A9/A12/A14: 4 個關鍵 advance 點必須有 deliverables
        for sub_id in ("1.1d", "2.7", "4.1d", "4.2"):
            sp = SUB_PHASES[sub_id]
            assert len(sp.deliverables_required) > 0, f"{sub_id} 缺 deliverables_required"
