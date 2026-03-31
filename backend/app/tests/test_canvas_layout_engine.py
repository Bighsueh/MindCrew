"""Tests for canvas layout engine (Phase 14, Step 14.6)."""

import pytest

from app.canvas.clustering import ClusterResult
from app.canvas.layout_engine import LayoutEngine, CoordinateUpdate
from app.canvas.spatial import SpatialNote, NOTE_WIDTH, NOTE_HEIGHT


def _make_note(
    id: str, x: float, y: float,
    width: float = NOTE_WIDTH, height: float = NOTE_HEIGHT,
) -> SpatialNote:
    return SpatialNote(
        id=id, text="test", x=x, y=y,
        width=width, height=height,
        color="yellow", author_type="human", created_at="",
    )


@pytest.fixture
def engine() -> LayoutEngine:
    return LayoutEngine()


class TestResolvePosition:
    def test_grid_format(self, engine: LayoutEngine) -> None:
        x, y = engine.resolve_position("grid:2,1", [])
        assert x > 0 and y > 0

    def test_near_format(self, engine: LayoutEngine) -> None:
        ref = _make_note("n1", 100, 100)
        x, y = engine.resolve_position("near:n1", [ref])
        # Should be adjacent to n1, not on top of it
        assert not (x == 100 and y == 100)

    def test_region_format(self, engine: LayoutEngine) -> None:
        x, y = engine.resolve_position("region:bottom-right", [])
        assert x > 0 and y > 0

    def test_cluster_format(self, engine: LayoutEngine) -> None:
        notes = [
            _make_note("n1", 100, 100),
            _make_note("n2", 150, 120),
        ]
        cluster = ClusterResult(
            cluster_id="c1", note_ids=["n1", "n2"],
            centroid=[0.0], coherence_score=0.9,
        )
        x, y = engine.resolve_position("cluster:c1", notes, clusters=[cluster])
        # Should be near the cluster members
        assert 0 < x < 2000
        assert 0 < y < 2000

    def test_fallback_on_invalid(self, engine: LayoutEngine) -> None:
        x, y = engine.resolve_position("invalid:xyz", [])
        assert x >= 0 and y >= 0


class TestComputeArrangement:
    def test_grid_layout(self, engine: LayoutEngine) -> None:
        notes = [_make_note(f"n{i}", i * 300, 0) for i in range(6)]
        ids = [f"n{i}" for i in range(6)]
        updates = engine.compute_arrangement(
            note_ids=ids, layout="grid", target_region="top-left",
            notes=notes, columns=3,
        )
        assert len(updates) == 6
        # Check non-overlapping: no two notes at same position
        positions = {(u.x, u.y) for u in updates}
        assert len(positions) == 6

    def test_horizontal_layout(self, engine: LayoutEngine) -> None:
        ids = ["n1", "n2", "n3"]
        notes = [_make_note(id, 0, 0) for id in ids]
        updates = engine.compute_arrangement(
            note_ids=ids, layout="horizontal", target_region="center",
            notes=notes,
        )
        assert len(updates) == 3
        # All same y, increasing x
        ys = {u.y for u in updates}
        assert len(ys) == 1  # all same row

    def test_vertical_layout(self, engine: LayoutEngine) -> None:
        ids = ["n1", "n2", "n3"]
        notes = [_make_note(id, 0, 0) for id in ids]
        updates = engine.compute_arrangement(
            note_ids=ids, layout="vertical", target_region="center",
            notes=notes,
        )
        assert len(updates) == 3
        xs = {u.x for u in updates}
        assert len(xs) == 1  # all same column

    def test_circular_layout(self, engine: LayoutEngine) -> None:
        ids = [f"n{i}" for i in range(5)]
        notes = [_make_note(id, 0, 0) for id in ids]
        updates = engine.compute_arrangement(
            note_ids=ids, layout="circular", target_region="center",
            notes=notes,
        )
        assert len(updates) == 5


class TestComputeTidy:
    def test_tidy_all(self, engine: LayoutEngine) -> None:
        notes = [_make_note(f"n{i}", i * 50, i * 50) for i in range(5)]
        updates = engine.compute_tidy(
            scope="all", target=None, strategy="align_grid",
            notes=notes,
        )
        assert len(updates) == 5

    def test_tidy_empty(self, engine: LayoutEngine) -> None:
        updates = engine.compute_tidy(
            scope="all", target=None, strategy="align_grid",
            notes=[],
        )
        assert len(updates) == 0


class TestCollisionDetection:
    def test_no_collision(self, engine: LayoutEngine) -> None:
        notes = [_make_note("n1", 0, 0)]
        assert not engine._has_collision(500, 500, NOTE_WIDTH, NOTE_HEIGHT, notes)

    def test_collision(self, engine: LayoutEngine) -> None:
        notes = [_make_note("n1", 0, 0)]
        assert engine._has_collision(50, 50, NOTE_WIDTH, NOTE_HEIGHT, notes)
