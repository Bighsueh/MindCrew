"""Tests for canvas tool interfaces (Phase 14, Steps 14.8-14.9).

Uses mocked dependencies to test tool logic without external services.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.canvas.spatial import SpatialNote
from app.canvas.clustering import ClusterResult, ClusterState
from app.canvas.analyzer import CanvasAnalysis


def _make_analysis(n_notes: int = 5) -> CanvasAnalysis:
    notes = [
        SpatialNote(
            id=f"n{i}", text=f"Text {i}",
            x=80 + (i % 5) * 260, y=80 + (i // 5) * 210,
            width=200, height=150,
            color="yellow", author_type="human", created_at="",
        )
        for i in range(n_notes)
    ]
    cluster = ClusterResult(
        cluster_id="c1", note_ids=[n.id for n in notes[:3]],
        centroid=[0.0], suggested_label="測試叢集",
        coherence_score=0.85,
    )
    return CanvasAnalysis(
        notes=notes,
        cluster_state=ClusterState(
            clusters=[cluster],
            ungrouped_note_ids=[n.id for n in notes[3:]],
        ),
        cluster_labels={"c1": "測試叢集"},
        orderliness_score=0.65,
        overlap_pairs=[],
        board_bounds={"used_area": "top-left to top-right", "free_regions": ["bottom-left", "bottom-right"]},
        free_regions=["bottom-left", "bottom-right"],
    )


@pytest.fixture
def mock_analyzer():
    with patch("app.canvas.tools_perception.get_spatial_analyzer") as m:
        analyzer = MagicMock()
        analyzer.analyze = AsyncMock(return_value=_make_analysis())
        m.return_value = analyzer
        yield analyzer


@pytest.mark.asyncio
async def test_get_canvas_summary(mock_analyzer: MagicMock) -> None:
    from app.canvas.tools_perception import get_canvas_summary
    result = await get_canvas_summary(uuid4())

    assert "summary" in result
    assert result["summary"]["total_notes"] == 5
    assert result["summary"]["cluster_count"] == 1
    assert result["summary"]["ungrouped_count"] == 2
    assert "clusters" in result
    assert len(result["clusters"]) == 1
    assert result["clusters"][0]["suggested_label"] == "測試叢集"


@pytest.mark.asyncio
async def test_get_canvas_snapshot(mock_analyzer: MagicMock) -> None:
    from app.canvas.tools_perception import get_canvas_snapshot
    result = await get_canvas_snapshot(uuid4())

    assert "summary" in result
    assert "notes" in result
    assert len(result["notes"]) == 5
    # Each note should have required fields
    note = result["notes"][0]
    assert "id" in note
    assert "text" in note
    assert "region" in note
    assert "grid_position" in note


@pytest.mark.asyncio
async def test_get_note_detail(mock_analyzer: MagicMock) -> None:
    from app.canvas.tools_perception import get_note_detail
    result = await get_note_detail(uuid4(), "n0")

    assert result is not None
    assert result["id"] == "n0"
    assert "neighbors" in result
    assert "pixel_position" in result


@pytest.mark.asyncio
async def test_get_note_detail_not_found(mock_analyzer: MagicMock) -> None:
    from app.canvas.tools_perception import get_note_detail
    result = await get_note_detail(uuid4(), "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_tool_swap_notes() -> None:
    """Test swap_notes swaps coordinates correctly."""
    project_id = uuid4()
    analysis = _make_analysis(2)

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_ops.batch_update_coordinates = AsyncMock(return_value=True)

        from app.canvas.tools_manipulation import tool_swap_notes
        result = await tool_swap_notes(project_id, "n0", "n1")

        assert result["success"] is True
        # Verify batch update was called with swapped coordinates
        call_args = mock_ops.batch_update_coordinates.call_args
        updates = call_args[1]["updates"] if "updates" in call_args[1] else call_args[0][1]
        assert len(updates) == 2


@pytest.mark.asyncio
async def test_tool_create_note() -> None:
    """Test create_note creates a note at resolved position."""
    project_id = uuid4()
    analysis = _make_analysis()

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
        patch("app.canvas.tools_manipulation.get_layout_engine") as mock_le,
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_sa.return_value.invalidate_semantic_cache = AsyncMock()
        mock_ops.add_note = AsyncMock(return_value="new_note_id")
        mock_le.return_value.resolve_position = MagicMock(return_value=(500.0, 300.0))

        from app.canvas.tools_manipulation import tool_create_note
        result = await tool_create_note(
            project_id=project_id,
            text="新觀點",
            position="cluster:c1",
        )

        assert result["success"] is True
        assert result["note_id"] == "new_note_id"
        # Verify semantic cache was invalidated
        mock_sa.return_value.invalidate_semantic_cache.assert_called_once()
