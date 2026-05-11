"""Tests for voting module (Spec 13, Step 17.8).

Voting requires Redis + canvas state; for unit tests we mock both.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.canvas.voting import (
    MIN_CANDIDATES,
    VOTE_SUB_PHASES,
    VoteOpenResult,
    open_vote,
)


pytestmark = pytest.mark.asyncio


@dataclass
class FakeNote:
    id: str
    x: float
    y: float
    color: str
    w: float = 160


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

    @classmethod
    def with_notes(cls, notes: list) -> "FakeAnalysis":
        return cls(notes=notes, cluster_state=FakeClusterState())


@pytest.fixture(autouse=True)
def _mock_redis_and_analyzer(monkeypatch):
    async def _empty_zones(*args, **kwargs):
        return {}

    # Stub Redis client used by open_vote
    class _FakeRedis:
        async def set(self, *a, **kw): pass
        async def delete(self, *a, **kw): pass
        async def get(self, *a, **kw): return None
        async def hincrby(self, *a, **kw): pass
        async def hgetall(self, *a, **kw): return {}
        async def aclose(self): pass

    async def _fake_get_redis():
        return _FakeRedis()

    monkeypatch.setattr("app.canvas.voting._get_redis", _fake_get_redis)
    monkeypatch.setattr("app.canvas.voting.get_all_zones_for_project", _empty_zones)


class _FakeAnalyzer:
    def __init__(self, notes):
        self._notes = notes

    async def analyze(self, project_id):
        return FakeAnalysis.with_notes(self._notes)

    async def invalidate_full_state_cache(self, project_id): pass
    async def invalidate_semantic_cache(self, project_id): pass


def _patch_analyzer(monkeypatch, notes):
    fake = _FakeAnalyzer(notes)
    monkeypatch.setattr(
        "app.canvas.voting.get_spatial_analyzer",
        lambda: fake,
    )


class TestVoteSubPhases:
    def test_only_2_6_and_4_1c(self) -> None:
        assert VOTE_SUB_PHASES == {"2.6", "4.1c"}


class TestOpenVote:
    async def test_rejects_wrong_sub_phase(self) -> None:
        result = await open_vote(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            current_sub_phase="2.2",
            opened_by="agent_supervisor",
        )
        assert result.success is False
        assert "2.6" in (result.error_zh or "")

    async def test_rejects_no_criteria(self, monkeypatch) -> None:
        # 5 yellow POV candidates but no green criteria
        notes = [
            FakeNote(id=f"pov-{i}", x=500, y=500 + i * 200, color="yellow")
            for i in range(MIN_CANDIDATES)
        ]
        _patch_analyzer(monkeypatch, notes)
        result = await open_vote(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            current_sub_phase="2.6",
            opened_by="agent_supervisor",
        )
        assert result.success is False
        assert "準則" in (result.error_zh or "")

    async def test_rejects_too_few_candidates(self, monkeypatch) -> None:
        # 3 green criteria（達到 Spec 14 A7 的 MIN_CRITERIA）, 1 POV (too few)
        notes = [
            FakeNote(id="crit-1", x=2200, y=200, color="green"),
            FakeNote(id="crit-2", x=2200, y=400, color="green"),
            FakeNote(id="crit-3", x=2200, y=600, color="green"),
            FakeNote(id="pov-1", x=500, y=500, color="yellow"),
        ]
        _patch_analyzer(monkeypatch, notes)
        result = await open_vote(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            current_sub_phase="2.6",
            opened_by="agent_supervisor",
        )
        assert result.success is False
        assert "候選" in (result.error_zh or "")

    async def test_rejects_too_few_criteria(self, monkeypatch) -> None:
        # Spec 14 A7: criteria < 3 應該被擋（即使候選夠）
        notes = [
            FakeNote(id="crit-1", x=2200, y=200, color="green"),
            FakeNote(id="pov-1", x=500, y=500, color="yellow"),
            FakeNote(id="pov-2", x=500, y=700, color="yellow"),
            FakeNote(id="pov-3", x=500, y=900, color="yellow"),
        ]
        _patch_analyzer(monkeypatch, notes)
        result = await open_vote(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            current_sub_phase="2.6",
            opened_by="agent_supervisor",
        )
        assert result.success is False
        assert "準則" in (result.error_zh or "")

    async def test_opens_when_criteria_and_candidates_present(self, monkeypatch) -> None:
        # Spec 14 A7: 需要 ≥3 criteria
        notes = [
            FakeNote(id="crit-1", x=2200, y=200, color="green"),
            FakeNote(id="crit-2", x=2200, y=400, color="green"),
            FakeNote(id="crit-3", x=2200, y=600, color="green"),
            FakeNote(id="pov-1", x=500, y=500, color="yellow"),
            FakeNote(id="pov-2", x=500, y=700, color="yellow"),
            FakeNote(id="pov-3", x=500, y=900, color="yellow"),
        ]
        _patch_analyzer(monkeypatch, notes)
        result = await open_vote(
            project_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
            current_sub_phase="2.6",
            opened_by="agent_supervisor",
        )
        assert result.success is True
        assert result.candidate_count == 3
        assert result.criteria_count == 3
