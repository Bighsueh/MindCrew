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


@pytest.mark.asyncio
async def test_tool_create_note_warmup_strips_group_id() -> None:
    """人本暖場：即使 LLM 自願帶 group_id，0.0a 也強制拿掉（保證暖場不分群）。"""
    project_id = uuid4()
    analysis = CanvasAnalysis(notes=[], cluster_state=ClusterState())

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
        patch(
            "app.canvas.tools_manipulation._resolve_concept_position",
            new=AsyncMock(return_value=(300.0, 200.0)),
        ),
        patch(
            "app.canvas.tools_manipulation._evaluate_create_gates",
            new=AsyncMock(return_value=__import__(
                "app.canvas.tools_manipulation", fromlist=["CreateNoteOutcome"],
            ).CreateNoteOutcome(success=True, zone_id="icebreaker_zone")),
        ),
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_sa.return_value.invalidate_semantic_cache = AsyncMock()
        mock_ops.add_note = AsyncMock(return_value="new_id")

        from app.canvas.tools_manipulation import tool_create_note
        result = await tool_create_note(
            project_id=project_id,
            text="我推購物車最怕輪子卡住",
            author_id="agent_crew_2",
            author_name="隊友B",
            author_type="ai",
            sub_phase_id="0.0a",
            group_id="購物車使用經驗",  # LLM 自願帶 → 應被拿掉
        )

        assert result["success"] is True
        assert result["group_id"] is None
        assert mock_ops.add_note.call_args.kwargs["group_id"] is None


@pytest.mark.asyncio
async def test_tool_create_note_warmup_per_agent_cap() -> None:
    """人本暖場：同一作者在 0.0a 已有 8 張內容便條 → 第 9 張被軟拒（Phase 42 B1 cap 8）。"""
    project_id = uuid4()
    author_tag = "張志強(ai)"
    notes = [
        SpatialNote(
            id=f"n{i}", text=f"暖場{i}", x=0, y=0, width=200, height=150,
            color="yellow", author_type="ai", created_at="",
            author_name=author_tag, kind="content",
        )
        for i in range(8)
    ]
    analysis = CanvasAnalysis(notes=notes, cluster_state=ClusterState())

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_ops.add_note = AsyncMock(return_value="new_id")

        from app.canvas.tools_manipulation import tool_create_note
        result = await tool_create_note(
            project_id=project_id,
            text="第三張便條",
            author_id="agent_x",
            author_name="張志強",
            author_type="ai",
            sub_phase_id="0.0a",
        )

        assert result["success"] is False
        assert result["rejection"]["rule_name"] == "warmup_per_agent_note_cap"
        mock_ops.add_note.assert_not_called()


@pytest.mark.asyncio
async def test_tool_create_note_backfills_group_id_when_llm_omits() -> None:
    """病根 B（基石）：接話式內容便條 LLM 漏帶 group_id → 由既有主題群確定性兜底後寫入。

    既有一張「顧客」群便條、文字與新便條夠相似（足以兜底、但不到去重門檻）→
    新便條應被補上 group_id='顧客' 並原樣傳給 canvas_ops.add_note。
    """
    from app.canvas.tools_manipulation import CreateNoteOutcome

    project_id = uuid4()
    existing = SpatialNote(
        id="e1", text="顧客覺得價格太貴", x=80, y=80, width=200, height=150,
        color="yellow", author_type="ai", created_at="",
        kind="content", concept_group_id="顧客",
    )
    analysis = CanvasAnalysis(
        notes=[existing], cluster_state=ClusterState(),
    )

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
        patch("app.canvas.tools_manipulation._is_threaded_sub_phase", return_value=True),
        patch(
            "app.canvas.tools_manipulation._resolve_concept_position",
            new=AsyncMock(return_value=(500.0, 300.0)),
        ),
        patch(
            "app.canvas.tools_manipulation._evaluate_create_gates",
            new=AsyncMock(return_value=CreateNoteOutcome(success=True, zone_id="z")),
        ),
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_sa.return_value.invalidate_semantic_cache = AsyncMock()
        mock_ops.add_note = AsyncMock(return_value="new_id")

        from app.canvas.tools_manipulation import tool_create_note
        result = await tool_create_note(
            project_id=project_id,
            text="顧客覺得價格便宜",  # 夠相似可兜底、未達去重門檻
            sub_phase_id="1.5",  # 真正的接話式分群格（非暖場；is_threaded 已 patch True）
            group_id=None,  # LLM 漏帶
        )

        assert result["success"] is True
        assert result["group_id"] == "顧客"
        assert mock_ops.add_note.call_args.kwargs["group_id"] == "顧客"


@pytest.mark.asyncio
async def test_tool_arrange_notes_label_tagged_as_label() -> None:
    """Spec 27 §6 / 病根 A：arrange_notes 自動建立的分類標籤必須帶 kind='label' + group_id。

    否則標籤被當成普通內容便條儲存，不被辨識為分類便條、不會序列化給 LLM、畫面上無區別
    ——直接導致「分類便條沒被擺出來」。
    """
    project_id = uuid4()
    analysis = _make_analysis(3)

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_sa.return_value.invalidate_semantic_cache = AsyncMock()
        mock_ops.batch_update_coordinates = AsyncMock(return_value=True)
        mock_ops.add_note = AsyncMock(return_value="label_note_id")

        from app.canvas.tools_manipulation import tool_arrange_notes
        result = await tool_arrange_notes(
            project_id=project_id,
            note_ids=["n0", "n1", "n2"],
            layout="grid",
            target_region="top-left",
            label="顧客",
            group_id="顧客",
        )

        assert result["success"] is True
        assert result.get("label_note_id") == "label_note_id"
        mock_ops.add_note.assert_called_once()
        kwargs = mock_ops.add_note.call_args.kwargs
        assert kwargs.get("kind") == "label", "標籤便條必須帶 kind='label'"
        assert kwargs.get("group_id") == "顧客", "標籤便條必須帶 group_id"


@pytest.mark.asyncio
async def test_tool_tidy_area_creates_missing_group_labels() -> None:
    """病根 E：整理時，已成形（≥3 張內容）卻無標籤的群 → 自動補一張 kind='label'。"""
    project_id = uuid4()
    notes = [
        SpatialNote(
            id=f"k{i}", text=f"顧客概念{i}", x=i * 50, y=i * 50,
            width=200, height=150, color="yellow", author_type="ai",
            created_at="", kind="content", concept_group_id="顧客",
        )
        for i in range(3)
    ]
    analysis = CanvasAnalysis(notes=notes, cluster_state=ClusterState())

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_sa.return_value.invalidate_semantic_cache = AsyncMock()
        mock_ops.batch_update_coordinates = AsyncMock(return_value=True)
        mock_ops.add_note = AsyncMock(return_value="lbl_id")

        from app.canvas.tools_manipulation import tool_tidy_area
        result = await tool_tidy_area(project_id, scope="all")

        assert result["success"] is True
        assert result["labels_created"] == 1
        mock_ops.add_note.assert_called_once()
        kwargs = mock_ops.add_note.call_args.kwargs
        assert kwargs["kind"] == "label"
        assert kwargs["group_id"] == "顧客"


@pytest.mark.asyncio
async def test_tool_tidy_area_repositions_existing_label_no_duplicate() -> None:
    """病根 E 冪等：群已有標籤 → 重定位（不重複建）。"""
    project_id = uuid4()
    notes = [
        SpatialNote(
            id=f"k{i}", text=f"顧客概念{i}", x=i * 50, y=i * 50,
            width=200, height=150, color="yellow", author_type="ai",
            created_at="", kind="content", concept_group_id="顧客",
        )
        for i in range(3)
    ] + [
        SpatialNote(
            id="lbl", text="顧客", x=9999, y=9999, width=200, height=150,
            color="blue", author_type="ai", created_at="",
            kind="label", concept_group_id="顧客",
        )
    ]
    analysis = CanvasAnalysis(notes=notes, cluster_state=ClusterState())

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_sa.return_value.invalidate_semantic_cache = AsyncMock()
        mock_ops.batch_update_coordinates = AsyncMock(return_value=True)
        mock_ops.add_note = AsyncMock(return_value="lbl_id")

        from app.canvas.tools_manipulation import tool_tidy_area
        result = await tool_tidy_area(project_id, scope="all")

        assert result["labels_created"] == 0
        mock_ops.add_note.assert_not_called()
        # 既有標籤被加入 batch 重定位
        batch = mock_ops.batch_update_coordinates.call_args[0][1]
        assert any(u["id"] == "lbl" for u in batch)


@pytest.mark.asyncio
async def test_tool_tidy_area_group_scope_moves_only_target_group() -> None:
    """spec 10 v2.0 §5.7 scope='group'（auto_reflow 保底原語）：只收攏目標群、
    他群一張不動、標籤補在該群錨點上方。"""
    project_id = uuid4()
    notes = [
        SpatialNote(
            id="k0", text="顧客概念0", x=300, y=300, width=200, height=150,
            color="yellow", author_type="ai", created_at="",
            kind="content", concept_group_id="顧客",
        ),
        SpatialNote(
            id="k1", text="顧客概念1", x=900, y=700, width=200, height=150,
            color="yellow", author_type="ai", created_at="",
            kind="content", concept_group_id="顧客",
        ),
        SpatialNote(
            id="k2", text="顧客概念2", x=1400, y=350, width=200, height=150,
            color="yellow", author_type="ai", created_at="",
            kind="content", concept_group_id="顧客",
        ),
        SpatialNote(
            id="d0", text="店員概念", x=300, y=1500, width=200, height=150,
            color="yellow", author_type="ai", created_at="",
            kind="content", concept_group_id="店員",
        ),
    ]
    analysis = CanvasAnalysis(notes=notes, cluster_state=ClusterState())

    with (
        patch("app.canvas.tools_manipulation.get_spatial_analyzer") as mock_sa,
        patch("app.canvas.tools_manipulation.canvas_ops") as mock_ops,
    ):
        mock_sa.return_value.analyze = AsyncMock(return_value=analysis)
        mock_sa.return_value.invalidate_semantic_cache = AsyncMock()
        mock_ops.batch_update_coordinates = AsyncMock(return_value=True)
        mock_ops.add_note = AsyncMock(return_value="lbl_id")

        from app.canvas.tools_manipulation import tool_tidy_area
        result = await tool_tidy_area(project_id, scope="group", target="顧客")

        assert result["success"] is True
        batch = mock_ops.batch_update_coordinates.call_args[0][1]
        moved_ids = {u["id"] for u in batch}
        assert "d0" not in moved_ids  # 他群不動
        assert moved_ids <= {"k0", "k1", "k2"}
        # 顧客群 ≥3 張無標籤 → 補一張、且只補目標群
        assert result["labels_created"] == 1
        assert mock_ops.add_note.call_args.kwargs["group_id"] == "顧客"


@pytest.mark.asyncio
async def test_tool_create_note_passes_meta_created_at() -> None:
    """Phase 24.A：tool_create_note 必須傳 created_at（ISO Z）給 canvas_ops.add_note。

    這是 Activity Highlight（聊天氣泡 ⇄ 便利貼）時間配對的前置條件——
    AI 建立的便利貼必須帶上時間戳，才能落在 30s 視窗內被高亮。
    """
    import re

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
        await tool_create_note(
            project_id=project_id,
            text="同作者高亮測試",
            position="cluster:c1",
        )

        mock_ops.add_note.assert_called_once()
        kwargs = mock_ops.add_note.call_args.kwargs
        assert "created_at" in kwargs, "add_note 必須收到 created_at kwarg"
        created_at = kwargs["created_at"]
        # ISO 8601 with Z suffix (UTC)
        assert isinstance(created_at, str)
        assert created_at.endswith("Z"), f"created_at 必須以 Z 結尾，實得: {created_at}"
        # 寬鬆驗證 ISO 格式 YYYY-MM-DDTHH:MM:SS(.ffffff)?Z
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$", created_at
        ), f"created_at 非 ISO Z 格式: {created_at}"
