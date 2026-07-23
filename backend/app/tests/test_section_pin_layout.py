"""WS4：版面工具保留 section/選定區成員（spec 27 §7 鐵律、canvas-DRAFT §1/§2）。

選定是空間承諾——`tidy_area`／`arrange_notes` 不得把落在動態 section 帶內的便條搬離其帶
（否則 closing 直讀選定區會漏算 chosen_problem_statements）。成員資格純由位置衍生
（`sections.selection_members`），人類拖出帶外即自動解除。
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.canvas import tools_manipulation as tm


def _async(value):
    async def _f(*a, **k):
        return value
    return _f


def _upd(note_id: str, x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(id=note_id, x=x, y=y)


def _patch_common(monkeypatch, analysis, *, members):
    monkeypatch.setattr(
        tm, "get_spatial_analyzer",
        lambda: SimpleNamespace(analyze=_async(analysis), invalidate_semantic_cache=_async(None)),
    )
    monkeypatch.setattr("app.canvas.sections.selection_members", _async(members))


# ── tidy_area ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tidy_area_preserves_selection_member(monkeypatch):
    pinned = SimpleNamespace(id="ps_sel", x=200.0, y=2100.0, concept_group_id=None, kind="content")
    free = SimpleNamespace(id="n_free", x=200.0, y=300.0, concept_group_id=None, kind="content")
    analysis = SimpleNamespace(notes=[pinned, free], cluster_state=SimpleNamespace(clusters=[]))
    _patch_common(monkeypatch, analysis, members=[pinned])

    # engine 想把兩張都重排回頂端 grid（y=230）。
    monkeypatch.setattr(tm, "get_layout_engine", lambda: SimpleNamespace(
        compute_tidy=lambda **k: [_upd("ps_sel", 100.0, 230.0), _upd("n_free", 300.0, 230.0)],
        compute_group_label_anchors=lambda **k: {},
    ))
    captured = {}

    async def fake_batch(pid, coord_updates, moved_by=None):
        captured["coords"] = coord_updates
        return True

    monkeypatch.setattr(tm.canvas_ops, "batch_update_coordinates", fake_batch)

    res = await tm.tool_tidy_area(uuid4(), scope="all", strategy="align_grid")
    ids = {c["id"] for c in captured["coords"]}
    assert "ps_sel" not in ids        # 選定區成員不被搬離其帶
    assert "n_free" in ids            # 一般便條照常重排
    assert res["pinned_skipped"] == 1
    assert res["tidied_count"] == 1


@pytest.mark.asyncio
async def test_tidy_no_section_is_passthrough(monkeypatch):
    # 無動態 section（2.6 前）→ pinned 空集 → 行為與今日一致。
    a = SimpleNamespace(id="a", x=10.0, y=10.0, concept_group_id=None, kind="content")
    b = SimpleNamespace(id="b", x=20.0, y=20.0, concept_group_id=None, kind="content")
    analysis = SimpleNamespace(notes=[a, b], cluster_state=SimpleNamespace(clusters=[]))
    _patch_common(monkeypatch, analysis, members=[])  # 無 section 成員
    monkeypatch.setattr(tm, "get_layout_engine", lambda: SimpleNamespace(
        compute_tidy=lambda **k: [_upd("a", 0.0, 0.0), _upd("b", 0.0, 0.0)],
        compute_group_label_anchors=lambda **k: {},
    ))
    captured = {}

    async def fake_batch(pid, coord_updates, moved_by=None):
        captured["coords"] = coord_updates
        return True

    monkeypatch.setattr(tm.canvas_ops, "batch_update_coordinates", fake_batch)

    res = await tm.tool_tidy_area(uuid4(), scope="all", strategy="align_grid")
    assert {c["id"] for c in captured["coords"]} == {"a", "b"}
    assert res["pinned_skipped"] == 0
    assert res["tidied_count"] == 2


# ── arrange_notes ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_arrange_notes_skips_selection_member(monkeypatch):
    pinned = SimpleNamespace(id="ps_sel", x=200.0, y=2100.0)
    free = SimpleNamespace(id="n_free", x=200.0, y=300.0)
    analysis = SimpleNamespace(notes=[pinned, free], cluster_state=SimpleNamespace(clusters=[]))
    _patch_common(monkeypatch, analysis, members=[pinned])

    seen = {}

    def fake_compute_arrangement(note_ids, **k):
        seen["note_ids"] = list(note_ids)
        return [_upd(i, 0.0, 0.0) for i in note_ids]

    monkeypatch.setattr(tm, "get_layout_engine",
                        lambda: SimpleNamespace(compute_arrangement=fake_compute_arrangement))
    monkeypatch.setattr(tm.canvas_ops, "batch_update_coordinates", _async(True))

    res = await tm.tool_arrange_notes(
        uuid4(), note_ids=["ps_sel", "n_free"], layout="grid", target_region="top-left",
    )
    assert seen["note_ids"] == ["n_free"]   # 選定區成員未進 compute_arrangement
    assert res["pinned_skipped"] == 1
    assert res["arranged_count"] == 1
