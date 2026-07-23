"""Tests for zone band model（RC1 修正）— spec 10 v2.0 §2.3 / spec 27 §5。

版面模型＝「phase 垂直堆疊 section 帶」：
  - 靜態 default_bounds 不得同原點塌陷——全部兩兩不相交（未註冊 fallback 也不疊）。
  - seed 時 zone bounds 由 section 模型推導：往白板最下方既有內容之下開帶。
  - snap 安全網：無同群錨點時帶內掃空位（不再堆 zone 中心）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.canvas import zone_seed as zs
from app.canvas.layout_engine import get_layout_engine
from app.canvas.tools_manipulation import _snap_into_active_zone
from app.canvas.zones import ZONES, Bounds, get_active_zones
from app.stages.sub_phases import SUB_PHASES


def _disjoint(a: Bounds, b: Bounds) -> bool:
    return (
        a.x + a.w <= b.x or b.x + b.w <= a.x
        or a.y + a.h <= b.y or b.y + b.h <= a.y
    )


# ---------------------------------------------------------------------------
# 靜態 default_bounds — 帶狀不塌陷
# ---------------------------------------------------------------------------


def test_all_default_bounds_pairwise_disjoint():
    """RC1 核心：7 個 zone 的 default_bounds 兩兩不相交（原本 5 個同錨 (100,100)）。"""
    zones = [z for z in ZONES.values() if z.default_bounds]
    assert len(zones) == len(ZONES)
    for i in range(len(zones)):
        for j in range(i + 1, len(zones)):
            assert _disjoint(zones[i].default_bounds, zones[j].default_bounds), (
                zones[i].id, zones[j].id,
            )


def test_bands_stack_top_down_in_first_use_order():
    """帶序＝各牆首次啟用的格序（spec 27 §5：舊 phase 在上、新 phase 往下開）。"""
    first_use_order = [
        "icebreaker_zone",          # 0.0a
        "stakeholder_public",       # 1.1b
        "pain_wall",                # 1.2
        "pov_wall",                 # 2.2
        "existing_solutions_zone",  # 2.4
        "define_criteria_sidebar",  # 2.5
        "hmw_dock",                 # 2.7
    ]
    ys = [ZONES[z].default_bounds.y for z in first_use_order]
    assert ys == sorted(ys)
    assert len(set(ys)) == len(ys)


def test_every_sub_phase_active_zones_disjoint():
    for sub_phase_id in SUB_PHASES:
        active = get_active_zones(sub_phase_id)
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                assert _disjoint(
                    active[i].default_bounds, active[j].default_bounds
                ), (sub_phase_id, active[i].id, active[j].id)


# ---------------------------------------------------------------------------
# seed-time banding — zone bounds 由 section 模型推導（spec 10 §2.3/§9.6）
# ---------------------------------------------------------------------------


@pytest.fixture()
def _seed_wire(monkeypatch):
    """接住 tool_draw_zone；registered 由假註冊表供應（無 Redis）。"""
    state: dict = {"registered": {}, "drawn": [], "content_bottom": 0.0}

    async def _fake_is_registered(project_id, zone_id):
        return zone_id in state["registered"]

    async def _fake_draw_zone(project_id, zone_id, bounds=None, **kwargs):
        state["drawn"].append({"zone_id": zone_id, "bounds": bounds})
        if bounds:
            state["registered"][zone_id] = bounds
        return {"success": True, "zone_id": zone_id, "bounds": bounds}

    async def _fake_content_bottom(project_id):
        bottom = state["content_bottom"]
        for b in state["registered"].values():
            bottom = max(bottom, b["y"] + b["h"])
        return bottom

    monkeypatch.setattr(zs, "is_zone_registered", _fake_is_registered)
    monkeypatch.setattr(zs, "tool_draw_zone", _fake_draw_zone)
    monkeypatch.setattr(zs, "compute_content_bottom", _fake_content_bottom)
    return state


@pytest.mark.asyncio
async def test_seed_empty_board_starts_at_top(_seed_wire):
    drawn = await zs.seed_zones_for_sub_phase(uuid4(), "0.0a")
    assert drawn == 1
    b = _seed_wire["drawn"][0]["bounds"]
    assert b["y"] == 100.0  # 空白板從頂端起
    assert b["w"] == ZONES["icebreaker_zone"].default_bounds.w


@pytest.mark.asyncio
async def test_seed_opens_band_below_existing_content(_seed_wire):
    _seed_wire["content_bottom"] = 1500.0  # 既有內容（前一帶＋便條）的下緣
    await zs.seed_zones_for_sub_phase(uuid4(), "1.1b")
    b = _seed_wire["drawn"][0]["bounds"]
    assert b["y"] == 1500.0 + 120.0  # bottom + SECTION_GAP
    assert b["h"] == ZONES["stakeholder_public"].default_bounds.h


@pytest.mark.asyncio
async def test_seed_multi_zone_phase_stacks_bands(_seed_wire):
    """2.6 宣告雙 zone：第二帶必須開在第一帶之下（不同原點、不相交）。"""
    _seed_wire["content_bottom"] = 3000.0
    drawn = await zs.seed_zones_for_sub_phase(uuid4(), "2.6")
    assert drawn == 2
    b1 = _seed_wire["drawn"][0]["bounds"]
    b2 = _seed_wire["drawn"][1]["bounds"]
    assert b2["y"] >= b1["y"] + b1["h"] + 120.0


@pytest.mark.asyncio
async def test_seed_skips_already_registered(_seed_wire):
    _seed_wire["registered"]["icebreaker_zone"] = {
        "x": 100.0, "y": 100.0, "w": 1700.0, "h": 1400.0,
    }
    drawn = await zs.seed_zones_for_sub_phase(uuid4(), "0.0a")
    assert drawn == 0
    assert _seed_wire["drawn"] == []


# ---------------------------------------------------------------------------
# snap 安全網 — 帶內掃空位（不再 zone 中心堆積）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_zone_registry(monkeypatch):
    async def _empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(
        "app.canvas.tools_manipulation.get_all_zones_for_project", _empty
    )


@pytest.mark.asyncio
async def test_snap_scans_band_slot_instead_of_center():
    """RC3 症狀之一：snap 以 zone 中心為種子 → 疊在同一點。改帶內掃空位。"""
    engine = get_layout_engine()
    x, y = await _snap_into_active_zone(99999, 99999, "0.0a", uuid4(), engine, [])
    b = ZONES["icebreaker_zone"].default_bounds
    assert b.contains(x, y)
    # 帶內掃描從左上內容列開始，不會落在帶中心。
    assert x < b.x + b.w / 2
    assert y < b.y + b.h / 2


@pytest.mark.asyncio
async def test_snap_successive_notes_do_not_stack(monkeypatch):
    """連兩張 out-of-zone 便條 snap 進帶 → 兩個不同、且不重疊的落點。"""
    from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH, SpatialNote

    engine = get_layout_engine()
    pid = uuid4()
    x1, y1 = await _snap_into_active_zone(99999, 99999, "0.0a", pid, engine, [])
    first = SpatialNote(
        id="n1", text="t", x=x1, y=y1, width=NOTE_WIDTH, height=NOTE_HEIGHT,
        color="yellow", author_type="ai", created_at="",
    )
    x2, y2 = await _snap_into_active_zone(99999, 99999, "0.0a", pid, engine, [first])
    assert (x1, y1) != (x2, y2)
    assert not (
        x2 < x1 + NOTE_WIDTH and x2 + NOTE_WIDTH > x1
        and y2 < y1 + NOTE_HEIGHT and y2 + NOTE_HEIGHT > y1
    )
