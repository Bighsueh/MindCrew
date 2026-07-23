"""Phase 42 D1c-前導：選定 PS 感知補完（修復定義 closing design_questions=0 真因）。

真因＝感知接線缺口（非 LLM 行為）：2.7 affordance 要 HMW 的 cites 指向選定問題定義，
但序列化白板不標記哪張是選定 PS、且最近 15 張截斷＋row-21 封存會把選定 PS 砍掉。
本測試釘住四個修正點：
- ``sections.selection_members`` 共用 helper（帶內/帶外/無 section）
- ``_normalize_canvas`` 讓 ``selected_ps`` 豁免 row-21 封存
- ``context_serializer`` 在 [-15:] 截斷前釘住「選定問題定義」區塊
- ``get_canvas_snapshot`` 每張便條帶 ``selected_ps`` + ``cites``
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.canvas.zones import Bounds

# 合法問題定義句（需求句型：「X 需要 Y，因為 Z」）。
_PS_TEXT = "上班族需要自動帶袋的方法，因為常常忘記"


def _note(**kw: object) -> SimpleNamespace:
    base: dict[str, object] = dict(
        id="n1", text="", x=0.0, y=0.0, cx=0.0, cy=0.0,
        color="yellow", author_type="ai", author_name="crew",
        kind="content", concept_group_id=None, cites=(),
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ── sections.selection_members ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_selection_members_returns_in_band_notes(monkeypatch):
    from app.canvas import sections

    band = Bounds(x=100.0, y=1000.0, w=2400.0, h=700.0)

    async def fake_bounds_map(_pid):
        return {"sec_x": band}

    monkeypatch.setattr(sections, "get_section_bounds_map", fake_bounds_map)

    inside = _note(id="in", x=200.0, y=1200.0)
    outside = _note(id="out", x=200.0, y=100.0)
    members = await sections.selection_members(uuid4(), [inside, outside])
    assert {n.id for n in members} == {"in"}


@pytest.mark.asyncio
async def test_selection_members_empty_when_no_section(monkeypatch):
    from app.canvas import sections

    async def fake_bounds_map(_pid):
        return {}

    monkeypatch.setattr(sections, "get_section_bounds_map", fake_bounds_map)
    members = await sections.selection_members(uuid4(), [_note(id="a", x=5.0, y=5.0)])
    assert members == []


# ── _normalize_canvas archive-row exemption ────────────────────────────────


def _snapshot(notes: list[dict]) -> dict:
    return {"summary": {"total_notes": len(notes)}, "notes": notes, "clusters": []}


def test_normalize_canvas_exempts_selected_ps_from_archive():
    from app.agents.context_buffer import _normalize_canvas

    selected_far = {"id": "ps", "text": "x", "grid_position": [0, 25], "selected_ps": True}
    normal_far = {"id": "old", "text": "y", "grid_position": [0, 25], "selected_ps": False}
    normal_near = {"id": "new", "text": "z", "grid_position": [0, 5], "selected_ps": False}

    out = _normalize_canvas(_snapshot([selected_far, normal_far, normal_near]))
    ids = {n["id"] for n in out["spatial_notes"]}
    assert "ps" in ids        # 選定 PS 落 row25 仍存活
    assert "new" in ids       # 近處便條保留
    assert "old" not in ids   # 非選定遠處便條被封存


# ── context_serializer pinned block ────────────────────────────────────────


def _ctx(spatial_notes: list[dict]) -> dict:
    return {
        "canvas_state": {
            "summary": {"total_notes": len(spatial_notes)},
            "spatial_notes": spatial_notes,
        }
    }


def test_serializer_pins_selected_ps_beyond_truncation():
    from app.agents.prompts.context_serializer import _append_canvas_state

    # 選定 PS 放第一張 → 落在最近 15 張視窗之外。
    ps = {"id": "PSID", "text": _PS_TEXT, "selected_ps": True}
    filler = [{"id": f"f{i}", "text": f"便條{i}", "selected_ps": False} for i in range(20)]
    parts: list[str] = []
    _append_canvas_state(parts, _ctx([ps, *filler]))
    out = "\n".join(parts)
    assert "選定問題定義" in out
    assert "PSID" in out


def test_serializer_no_block_when_no_selected_ps():
    from app.agents.prompts.context_serializer import _append_canvas_state

    notes = [{"id": f"f{i}", "text": f"便條{i}", "selected_ps": False} for i in range(3)]
    parts: list[str] = []
    _append_canvas_state(parts, _ctx(notes))
    assert "選定問題定義" not in "\n".join(parts)


# ── get_canvas_snapshot tagging ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_canvas_snapshot_tags_selected_ps_and_cites(monkeypatch):
    from app.canvas import tools_perception as tp

    ps = _note(id="ps", text=_PS_TEXT, x=200.0, y=1200.0, cites=("pain1", "pain2"))
    plain = _note(id="plain", text="一般便條", x=10.0, y=10.0)
    analysis = SimpleNamespace(notes=[ps, plain], overlap_pairs=[])

    async def fake_analyze(_pid):
        return analysis

    monkeypatch.setattr(tp, "get_spatial_analyzer", lambda: SimpleNamespace(analyze=fake_analyze))

    async def fake_summary(_pid, micro_phase=None):
        return {"summary": {"total_notes": 2}}

    monkeypatch.setattr(tp, "get_canvas_summary", fake_summary)
    monkeypatch.setattr(tp, "_build_cluster_map", lambda a: {})
    monkeypatch.setattr(tp, "_overlap_note_ids", lambda a: set())

    async def fake_members(_pid, notes):
        return [ps]

    monkeypatch.setattr(tp, "selection_members", fake_members)

    snap = await tp.get_canvas_snapshot(uuid4())
    by_id = {n["id"]: n for n in snap["notes"]}
    assert by_id["ps"]["selected_ps"] is True
    assert by_id["ps"]["cites"] == ["pain1", "pain2"]
    assert by_id["plain"]["selected_ps"] is False
