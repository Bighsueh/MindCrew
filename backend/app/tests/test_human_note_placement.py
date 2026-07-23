"""#5 便條重疊：人類絕對座標落點 — placement-time per-note 避讓（只動新那張）。

鐵律（spec 27 v2.5 §7「發散＝貼了就不動別人」）：
  - 點擊處無重疊 → 精確尊重點擊座標（不 jitter / 不 snap，維持 Spec 13 精準落點）。
  - 點擊處有重疊 → per-note 避讓到鄰近不重疊位，且**既有便條永不被移動**。
  - AI / system 絕對座標維持原樣（語意由呼叫端決定，不在此改）。

以真實 LayoutEngine + 假 analysis（SimpleNamespace）測；不需 DB。
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.canvas.layout_engine import get_layout_engine
from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH, SpatialNote
from app.canvas.tools_manipulation import _resolve_concept_position


def _note(nid: str, x: float, y: float) -> SpatialNote:
    return SpatialNote(
        id=nid, text="x", x=x, y=y, width=NOTE_WIDTH, height=NOTE_HEIGHT,
        color="yellow", author_type="ai", created_at="",
    )


async def _resolve(position: str, author_type: str, notes: list[SpatialNote]):
    return await _resolve_concept_position(
        position=position,
        group_id=None,
        is_threaded=False,
        engine=get_layout_engine(),
        analysis=SimpleNamespace(
            notes=notes, cluster_state=SimpleNamespace(clusters=[])
        ),
        project_id=uuid4(),
        sub_phase_id=None,
        author_type=author_type,
    )


@pytest.mark.asyncio
async def test_human_absolute_on_empty_area_keeps_exact_click() -> None:
    """空白處：精確尊重點擊座標（不 jitter、不 snap）。"""
    far = [_note("a", 5000.0, 5000.0)]  # 遠處，不擋點擊
    x, y = await _resolve("absolute:120,340", "human", far)
    assert (x, y) == (120.0, 340.0)


@pytest.mark.asyncio
async def test_human_absolute_on_collision_nudges_only_new_note() -> None:
    """點到既有便條上：避讓到不重疊位，且既有便條座標完全不動。"""
    existing = [_note("a", 200.0, 200.0)]
    before = (existing[0].x, existing[0].y)
    x, y = await _resolve("absolute:200,200", "human", existing)
    engine = get_layout_engine()
    assert not engine._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, existing)
    assert (x, y) != (200.0, 200.0)  # 確實避讓了
    assert (existing[0].x, existing[0].y) == before  # 既有便條未被移動


@pytest.mark.asyncio
async def test_ai_absolute_is_ignored_and_avoids_collision() -> None:
    """Phase E（spec 10 v2.0 §5.1）：absolute: 為人類專用——AI 給絕對座標
    一律忽略、改走系統落點（不會疊在既有便條上）。

    取代舊「AI 絕對座標維持原樣」行為（該逃生口已封鎖，見 test_prompt_contract）。
    """
    existing = [_note("a", 200.0, 200.0)]
    x, y = await _resolve("absolute:200,200", "ai", existing)
    engine = get_layout_engine()
    assert not engine._has_collision(x, y, NOTE_WIDTH, NOTE_HEIGHT, existing)
