"""Unit tests for build_canvas_topic_summary。

驗證重點：
  - 空白板（total_notes=0）→ 回空字串。
  - 有 cluster 時，摘要包含「便條紙 N 張」、cluster 標籤、密度中文化。
  - get_canvas_summary 例外時，swallow 並回空字串（不阻擋 Coach）。
  - 長度上限 ≤ 300 字元。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.coach.canvas_context import build_canvas_topic_summary


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_canvas_returns_empty_string() -> None:
    fake = {
        "summary": {"total_notes": 0, "cluster_count": 0, "orderliness_score": 0.0},
        "clusters": [],
        "organization_hint": "",
    }
    with patch(
        "app.canvas.tools_perception.get_canvas_summary",
        new=AsyncMock(return_value=fake),
    ):
        result = await build_canvas_topic_summary(uuid4(), "empathy_map")
    assert result == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_populated_canvas_summary_contains_key_fields() -> None:
    fake = {
        "summary": {
            "total_notes": 12,
            "cluster_count": 3,
            "orderliness_score": 0.72,
            "overlap_count": 1,
            "ungrouped_count": 2,
        },
        "clusters": [
            {"suggested_label": "工作壓力", "note_count": 5, "density": "dense"},
            {"suggested_label": "家庭關係", "note_count": 4, "density": "dense"},
            {"suggested_label": "其他", "note_count": 1, "density": "sparse"},
        ],
        "organization_hint": "建議把『其他』那群再展開",
    }
    with patch(
        "app.canvas.tools_perception.get_canvas_summary",
        new=AsyncMock(return_value=fake),
    ):
        result = await build_canvas_topic_summary(uuid4(), "empathy_map")

    assert "便條紙 12 張" in result
    assert "分群 3 群" in result
    assert "整齊度 0.7" in result
    assert "工作壓力" in result
    assert "密集" in result  # density=dense → 密集
    assert "建議把" in result  # organization_hint 有帶入
    assert len(result) <= 300


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_canvas_summary_failure_returns_empty() -> None:
    with patch(
        "app.canvas.tools_perception.get_canvas_summary",
        new=AsyncMock(side_effect=RuntimeError("analyzer down")),
    ):
        result = await build_canvas_topic_summary(uuid4(), "empathy_map")
    assert result == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_long_cluster_list_is_truncated_within_limit() -> None:
    fake = {
        "summary": {
            "total_notes": 100,
            "cluster_count": 20,
            "orderliness_score": 0.5,
            "overlap_count": 0,
            "ungrouped_count": 0,
        },
        "clusters": [
            {
                "suggested_label": f"分群標籤好長好長好長好長好長{i}",
                "note_count": 5,
                "density": "dense",
            }
            for i in range(20)
        ],
        "organization_hint": "x" * 500,
    }
    with patch(
        "app.canvas.tools_perception.get_canvas_summary",
        new=AsyncMock(return_value=fake),
    ):
        result = await build_canvas_topic_summary(uuid4(), "empathy_map")
    assert len(result) <= 300
    assert result.endswith("…") or len(result) < 300
