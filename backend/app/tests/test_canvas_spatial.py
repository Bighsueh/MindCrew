"""Tests for canvas spatial computations (Phase 14, Step 14.3)."""

import pytest

from app.canvas.spatial import (
    SpatialNote,
    assign_grid_position,
    assign_region,
    compute_board_bounds,
    compute_orderliness,
    compute_proximity_matrix,
    detect_overlaps,
    find_free_regions,
    find_neighbors,
)


def _make_note(
    id: str, x: float, y: float,
    width: float = 200, height: float = 150,
    text: str = "test",
) -> SpatialNote:
    return SpatialNote(
        id=id, text=text, x=x, y=y,
        width=width, height=height,
        color="yellow", author_type="human", created_at="",
    )


class TestOverlapDetection:
    def test_no_overlap(self) -> None:
        notes = [_make_note("n1", 0, 0), _make_note("n2", 300, 0)]
        assert detect_overlaps(notes) == []

    def test_overlap(self) -> None:
        notes = [_make_note("n1", 0, 0), _make_note("n2", 100, 50)]
        pairs = detect_overlaps(notes)
        assert len(pairs) == 1
        assert ("n1", "n2") in pairs

    def test_empty(self) -> None:
        assert detect_overlaps([]) == []

    def test_single_note(self) -> None:
        assert detect_overlaps([_make_note("n1", 0, 0)]) == []


class TestProximityMatrix:
    def test_shape(self) -> None:
        notes = [_make_note("n1", 0, 0), _make_note("n2", 100, 0), _make_note("n3", 0, 100)]
        mat = compute_proximity_matrix(notes)
        assert mat.shape == (3, 3)
        assert mat[0][0] == 0.0
        assert mat[0][1] > 0

    def test_empty(self) -> None:
        mat = compute_proximity_matrix([])
        assert mat.shape == (0, 0)


class TestOrderliness:
    def test_perfectly_aligned(self) -> None:
        """Notes in a perfect grid should have high orderliness."""
        notes = [
            _make_note("n1", 80, 80),
            _make_note("n2", 340, 80),
            _make_note("n3", 80, 290),
            _make_note("n4", 340, 290),
        ]
        score = compute_orderliness(notes)
        assert score > 0.5

    def test_scattered(self) -> None:
        """Randomly scattered overlapping notes should have low orderliness."""
        notes = [
            _make_note("n1", 50, 50),
            _make_note("n2", 60, 55),
            _make_note("n3", 70, 45),
            _make_note("n4", 800, 800),
            _make_note("n5", 55, 60),
        ]
        score = compute_orderliness(notes)
        assert score < 0.7

    def test_single_note(self) -> None:
        assert compute_orderliness([_make_note("n1", 0, 0)]) == 1.0


class TestRegionAssignment:
    def test_top_left(self) -> None:
        region = assign_region(100, 100)
        assert "top" in region
        assert "left" in region

    def test_grid_position(self) -> None:
        col, row = assign_grid_position(80, 80)
        assert col == 0
        assert row == 0

        col2, row2 = assign_grid_position(340, 290)
        assert col2 == 1
        assert row2 == 1


class TestFreeRegions:
    def test_all_free_when_empty(self) -> None:
        regions = find_free_regions([])
        assert len(regions) == 6  # 2 rows × 3 cols

    def test_some_occupied(self) -> None:
        notes = [_make_note("n1", 100, 100)]  # top-left
        regions = find_free_regions(notes)
        assert "top-left" not in regions
        assert len(regions) == 5


class TestBoardBounds:
    def test_empty(self) -> None:
        bounds = compute_board_bounds([])
        assert bounds["used_area"] == "empty"

    def test_with_notes(self) -> None:
        notes = [_make_note("n1", 100, 100)]
        bounds = compute_board_bounds(notes)
        assert bounds["used_area"] != "empty"
        assert "free_regions" in bounds


class TestNeighbors:
    def test_finds_neighbor(self) -> None:
        notes = [
            _make_note("n1", 0, 0),
            _make_note("n2", 250, 0),
        ]
        neighbors = find_neighbors("n1", notes)
        assert len(neighbors) == 1
        assert neighbors[0]["id"] == "n2"
        assert neighbors[0]["direction"] == "right"

    def test_no_distant_neighbors(self) -> None:
        notes = [
            _make_note("n1", 0, 0),
            _make_note("n2", 5000, 5000),
        ]
        neighbors = find_neighbors("n1", notes, max_distance=400)
        assert len(neighbors) == 0

    def test_nonexistent_note(self) -> None:
        assert find_neighbors("missing", []) == []
