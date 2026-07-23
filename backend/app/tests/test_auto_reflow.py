"""Tests for auto_reflow — 依狀態自動觸發的確定性版面保底（RC4）。

Spec 依據：
  - spec 10 v2.0 §5.8 碰撞讓位（白板上不留重疊、讓位限本帶、歸因系統讓位）
  - spec 27 §7 鐵律（永不整面重排、每次只動少數便條、選定區成員 pin、
    只在收斂階段整理、發散只貼不搬）
"""

from __future__ import annotations

import types
from dataclasses import replace
from uuid import uuid4

import pytest

from app.canvas import auto_reflow as ar
from app.canvas.auto_reflow import (
    _MAX_YIELD_PER_RUN,
    _pick_yield_victim,
    maybe_auto_reflow,
    plan_overlap_yields,
)
from app.canvas.layout_engine import get_layout_engine
from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH, SpatialNote, detect_overlaps
from app.canvas.zones import Bounds

def _note(
    nid: str,
    x: float,
    y: float,
    *,
    author_type: str = "ai",
    created_at: str = "2026-07-03T00:00:00Z",
    group: str | None = None,
    kind: str = "content",
) -> SpatialNote:
    return SpatialNote(
        id=nid,
        text=f"note {nid}",
        x=x,
        y=y,
        width=NOTE_WIDTH,
        height=NOTE_HEIGHT,
        color="yellow",
        author_type=author_type,
        created_at=created_at,
        kind=kind,
        concept_group_id=group,
    )


# ---------------------------------------------------------------------------
# _pick_yield_victim — 挑「誰讓位」
# ---------------------------------------------------------------------------


def test_victim_prefers_later_created_ai_note():
    a = _note("a", 100, 100, created_at="2026-07-03T00:00:00Z")
    b = _note("b", 110, 110, created_at="2026-07-03T00:01:00Z")
    assert _pick_yield_victim(a, b, pinned_ids=set()).id == "b"


def test_victim_prefers_ai_over_human():
    human = _note("h", 100, 100, author_type="human")
    ai = _note("a", 110, 110, created_at="2026-07-01T00:00:00Z")
    assert _pick_yield_victim(human, ai, pinned_ids=set()).id == "a"


def test_victim_none_when_both_human():
    h1 = _note("h1", 100, 100, author_type="human")
    h2 = _note("h2", 110, 110, author_type="human")
    assert _pick_yield_victim(h1, h2, pinned_ids=set()) is None


def test_victim_skips_pinned_section_member():
    a = _note("a", 100, 100)
    b = _note("b", 110, 110, created_at="2026-07-03T00:01:00Z")
    # b（較晚貼）被 pin → 改動 a；兩張都 pin → 都不動。
    assert _pick_yield_victim(a, b, pinned_ids={"b"}).id == "a"
    assert _pick_yield_victim(a, b, pinned_ids={"a", "b"}) is None


# ---------------------------------------------------------------------------
# plan_overlap_yields — 讓位計畫（純函式）
# ---------------------------------------------------------------------------


def test_yield_resolves_overlap_and_moves_only_one_note():
    engine = get_layout_engine()
    notes = [_note("a", 100, 100), _note("b", 120, 120, created_at="2026-07-03T01:00:00Z")]
    pairs = detect_overlaps(notes)
    assert pairs  # precondition：確實重疊

    updates = plan_overlap_yields(notes, pairs, set(), [], engine)

    assert len(updates) == 1
    assert updates[0].id == "b"
    moved = replace(notes[1], x=updates[0].x, y=updates[0].y)
    assert not detect_overlaps([notes[0], moved])


def test_yield_caps_moves_per_run():
    engine = get_layout_engine()
    notes = []
    # 5 對互不相干的重疊（相隔很遠）→ 一輪最多只搬 _MAX_YIELD_PER_RUN 張。
    for i in range(5):
        base_y = 100 + i * 800
        notes.append(_note(f"a{i}", 100, base_y))
        notes.append(_note(f"b{i}", 120, base_y + 20, created_at="2026-07-03T01:00:00Z"))
    pairs = detect_overlaps(notes)
    assert len(pairs) == 5

    updates = plan_overlap_yields(notes, pairs, set(), [], engine)
    assert len(updates) == _MAX_YIELD_PER_RUN


def test_yield_skips_all_human_pair():
    engine = get_layout_engine()
    notes = [
        _note("h1", 100, 100, author_type="human"),
        _note("h2", 120, 120, author_type="human"),
    ]
    updates = plan_overlap_yields(notes, detect_overlaps(notes), set(), [], engine)
    assert updates == []


def test_yield_stays_within_band_when_note_in_band():
    """讓位限本帶（spec 10 §5.8）：落點必須留在原 band 內。"""
    engine = get_layout_engine()
    band = Bounds(x=100, y=100, w=2000, h=800)
    notes = [_note("a", 300, 300), _note("b", 320, 320, created_at="2026-07-03T01:00:00Z")]

    updates = plan_overlap_yields(notes, detect_overlaps(notes), set(), [band], engine)

    assert len(updates) == 1
    u = updates[0]
    assert band.contains(u.x, u.y)
    assert band.contains(u.x + NOTE_WIDTH, u.y + NOTE_HEIGHT)


def test_yield_second_pair_sees_first_relocation():
    """三張互疊：第一張讓位後，第二對的碰撞檢查要看到新位置（不會撞回去）。"""
    engine = get_layout_engine()
    notes = [
        _note("a", 100, 100),
        _note("b", 110, 110, created_at="2026-07-03T01:00:00Z"),
        _note("c", 120, 120, created_at="2026-07-03T02:00:00Z"),
    ]
    updates = plan_overlap_yields(notes, detect_overlaps(notes), set(), [], engine)

    final = {n.id: n for n in notes}
    for u in updates:
        final[u.id] = replace(final[u.id], x=u.x, y=u.y)
    assert not detect_overlaps(list(final.values()))


# ---------------------------------------------------------------------------
# maybe_auto_reflow — 編排（節流／收斂 gating／cooldown）
# ---------------------------------------------------------------------------


class _FakeAnalyzer:
    def __init__(self, analysis):
        self._analysis = analysis
        self.invalidated = 0

    async def invalidate_full_state_cache(self, project_id):
        self.invalidated += 1

    async def analyze(self, project_id, *, fresh: bool = False):
        return self._analysis


def _analysis(notes, orderliness=1.0):
    return types.SimpleNamespace(
        notes=notes,
        overlap_pairs=detect_overlaps(notes),
        orderliness_score=orderliness,
        cluster_state=types.SimpleNamespace(clusters=[]),
    )


@pytest.fixture()
def _wire(monkeypatch):
    """接線假件：無 Redis、無 sidecar、無聊天匯流排。回傳可觀察的記錄器。"""
    calls: dict = {"batch": [], "tidy": [], "narrate": [], "ts": {}}

    async def _fake_get_ts(key):
        return calls["ts"].get(key)

    async def _fake_set_ts(key, value):
        calls["ts"][key] = value

    async def _fake_batch(project_id, updates, moved_by=None):
        calls["batch"].append({"updates": updates, "moved_by": moved_by})
        return True

    async def _fake_tidy(project_id, scope, target=None, strategy="align_grid", moved_by=None):
        calls["tidy"].append({"scope": scope, "target": target, "moved_by": moved_by})
        return {"success": True, "tidied_count": 2, "pinned_skipped": 0}

    async def _fake_narrate(project_id, content):
        calls["narrate"].append(content)

    async def _no_pins(project_id, notes):
        return set()

    async def _no_zones(project_id):
        return {}

    async def _no_sections(project_id):
        return {}

    monkeypatch.setattr(ar, "_get_ts", _fake_get_ts)
    monkeypatch.setattr(ar, "_set_ts", _fake_set_ts)
    monkeypatch.setattr(ar.canvas_ops, "batch_update_coordinates", _fake_batch)
    monkeypatch.setattr(ar, "tool_tidy_area", _fake_tidy)
    monkeypatch.setattr(ar, "_publish_narration", _fake_narrate)
    monkeypatch.setattr(ar, "_section_pinned_ids", _no_pins)
    monkeypatch.setattr(ar, "get_all_zones_for_project", _no_zones)
    monkeypatch.setattr(ar, "get_section_bounds_map", _no_sections)
    return calls


@pytest.mark.asyncio
async def test_reflow_yields_overlaps_with_system_attribution(_wire, monkeypatch):
    # 2.1＝收斂：讓位開啟（無群、無低有序度 → 不觸發群整理）。
    notes = [_note("a", 100, 100), _note("b", 120, 120, created_at="2026-07-03T01:00:00Z")]
    monkeypatch.setattr(
        ar, "get_spatial_analyzer", lambda: _FakeAnalyzer(_analysis(notes))
    )

    result = await maybe_auto_reflow(uuid4(), "2.1")

    assert result.yielded == 1
    assert len(_wire["batch"]) == 1
    assert _wire["batch"][0]["moved_by"] == "系統讓位"
    assert _wire["tidy"] == []


@pytest.mark.asyncio
async def test_reflow_no_yield_in_divergent_phase(_wire, monkeypatch):
    """spec 27 §7「發散＝貼了就不動別人」：發散期不做事後讓位。"""
    notes = [_note("a", 100, 100), _note("b", 120, 120, created_at="2026-07-03T01:00:00Z")]
    monkeypatch.setattr(
        ar, "get_spatial_analyzer", lambda: _FakeAnalyzer(_analysis(notes))
    )

    result = await maybe_auto_reflow(uuid4(), "1.1b")

    assert result.yielded == 0
    assert _wire["batch"] == []
    assert _wire["tidy"] == []


@pytest.mark.asyncio
async def test_reflow_throttled_within_min_interval(_wire, monkeypatch):
    notes = [_note("a", 100, 100), _note("b", 120, 120)]
    monkeypatch.setattr(
        ar, "get_spatial_analyzer", lambda: _FakeAnalyzer(_analysis(notes))
    )
    pid = uuid4()
    first = await maybe_auto_reflow(pid, "2.1")
    second = await maybe_auto_reflow(pid, "2.1")

    assert first.skipped is None
    assert second.skipped == "throttled"
    assert len(_wire["batch"]) == 1


@pytest.mark.asyncio
async def test_reflow_group_tidy_only_in_convergent_phase(_wire, monkeypatch):
    notes = [
        _note("a", 100, 100, group="g1"),
        _note("b", 900, 900, group="g1"),
        _note("c", 1500, 300, group="g1"),
    ]
    monkeypatch.setattr(
        ar, "get_spatial_analyzer",
        lambda: _FakeAnalyzer(_analysis(notes, orderliness=0.1)),
    )

    # 發散（1.1b）→ 不整理；收斂（2.1）→ 對單一群 tidy ＋ 聊天交代。
    await maybe_auto_reflow(uuid4(), "1.1b")
    assert _wire["tidy"] == []

    await maybe_auto_reflow(uuid4(), "2.1")
    assert len(_wire["tidy"]) == 1
    assert _wire["tidy"][0]["scope"] == "group"
    assert _wire["tidy"][0]["target"] == "g1"
    assert len(_wire["narrate"]) == 1


@pytest.mark.asyncio
async def test_reflow_group_tidy_respects_cooldown(_wire, monkeypatch):
    notes = [
        _note("a", 100, 100, group="g1"),
        _note("b", 900, 900, group="g1"),
    ]
    monkeypatch.setattr(
        ar, "get_spatial_analyzer",
        lambda: _FakeAnalyzer(_analysis(notes, orderliness=0.1)),
    )
    pid = uuid4()
    _wire["ts"][f"project:{pid}:last_tidy_ts"] = ar._now()  # 剛整理過

    await maybe_auto_reflow(pid, "2.1")
    assert _wire["tidy"] == []


@pytest.mark.asyncio
async def test_reflow_high_orderliness_no_tidy(_wire, monkeypatch):
    notes = [
        _note("a", 100, 100, group="g1"),
        _note("b", 900, 900, group="g1"),
    ]
    monkeypatch.setattr(
        ar, "get_spatial_analyzer",
        lambda: _FakeAnalyzer(_analysis(notes, orderliness=0.9)),
    )
    await maybe_auto_reflow(uuid4(), "2.1")
    assert _wire["tidy"] == []


@pytest.mark.asyncio
async def test_reflow_noop_on_clean_board(_wire, monkeypatch):
    notes = [_note("a", 100, 100), _note("b", 900, 900)]
    monkeypatch.setattr(
        ar, "get_spatial_analyzer", lambda: _FakeAnalyzer(_analysis(notes))
    )
    result = await maybe_auto_reflow(uuid4(), "1.1b")
    assert result.yielded == 0
    assert _wire["batch"] == []
