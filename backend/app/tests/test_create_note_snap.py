"""Tests for zone-aware note placement (snap into active zone).

Bug: AI create_note defaulting to `region:center` resolved to board centre
(~790,1000), which falls outside the 1.1a `icebreaker_zone` (y∈[100,500]) → every
note hard-rejected with `no_active_zone` → empty canvas. The snap pulls out-of-zone
coordinates into the sub_phase's active zone so the gate accepts them.
"""

from __future__ import annotations

import types
from uuid import uuid4

import pytest

from app.canvas.layout_engine import get_layout_engine
from app.canvas.tools_manipulation import (
    _resolve_concept_position,
    _snap_into_active_zone,
)
from app.canvas.zones import ZONES, resolve_zone_by_position

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _mock_registry(monkeypatch):
    """No Redis: registered bounds empty → snap & gate both use default_bounds."""
    async def _empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(
        "app.canvas.tools_manipulation.get_all_zones_for_project", _empty
    )


def _analysis(notes=None):
    return types.SimpleNamespace(
        notes=notes or [],
        cluster_state=types.SimpleNamespace(clusters=[]),
    )


async def test_snap_pulls_board_centre_into_icebreaker():
    """The exact bug coordinate (790,1000) must end up inside icebreaker_zone."""
    engine = get_layout_engine()
    x, y = await _snap_into_active_zone(790, 1000, "0.0a", uuid4(), engine, [])
    bounds = ZONES["icebreaker_zone"].default_bounds
    assert bounds.contains(x, y), (x, y)
    # And the create gate's zone resolution would now accept it.
    assert resolve_zone_by_position(x, y, "0.0a", project_zone_bounds={}) is not None


async def test_snap_noop_when_already_in_zone():
    engine = get_layout_engine()
    x, y = await _snap_into_active_zone(300, 300, "0.0a", uuid4(), engine, [])
    assert (x, y) == (300, 300)


async def test_grow_zone_to_contain_expands_instead_of_clamping(monkeypatch):
    """落在框外的非重疊落點 → 長大 zone 容納（不 clamp、不疊）。"""
    from app.canvas import tools_manipulation as tm
    from app.canvas.zones import Bounds

    captured: dict = {}

    async def _fake_register(pid, zid, bounds):
        captured["bounds"] = bounds

    monkeypatch.setattr(tm, "register_zone", _fake_register)
    b = Bounds(x=100, y=100, w=400, h=300)  # x∈[100,500], y∈[100,400]
    await tm._grow_zone_to_contain(uuid4(), "icebreaker_zone", b, 900, 700)
    nb = captured["bounds"]
    # grown to contain the whole note rect at (900,700) + margin
    assert nb.contains(900, 700)
    assert nb.contains(900 + 200, 700 + 150)
    assert nb.w > b.w and nb.h > b.h


async def test_grow_zone_noop_when_already_contained(monkeypatch):
    from app.canvas import tools_manipulation as tm
    from app.canvas.zones import Bounds

    called = {"n": 0}

    async def _fake_register(pid, zid, bounds):
        called["n"] += 1

    monkeypatch.setattr(tm, "register_zone", _fake_register)
    b = Bounds(x=100, y=100, w=1700, h=1400)
    await tm._grow_zone_to_contain(uuid4(), "icebreaker_zone", b, 300, 300)
    assert called["n"] == 0  # already contained → no re-register


async def test_snap_returns_original_when_no_active_zone():
    """Unknown/zoneless sub_phase → no target zone → original coords (gate decides)."""
    engine = get_layout_engine()
    x, y = await _snap_into_active_zone(999999, 999999, "9.9", uuid4(), engine, [])
    assert (x, y) == (999999, 999999)


async def test_resolve_absolute_is_not_snapped():
    """Human exact-drop (absolute:) must be respected, never snapped into a zone.

    Phase E（spec 10 v2.0 §5.1）：absolute: 為人類專用——AI 的 absolute 逃生口
    已封鎖（見 test_prompt_contract），故此處明示 author_type="human"。
    """
    engine = get_layout_engine()
    x, y = await _resolve_concept_position(
        position="absolute:5000,5000",
        group_id=None,
        is_threaded=False,
        engine=engine,
        analysis=_analysis(),
        project_id=uuid4(),
        sub_phase_id="0.0a",
        author_type="human",
    )
    assert (x, y) == (5000, 5000)


async def test_resolve_region_center_lands_in_zone_in_1_1a():
    """End-to-end of the fix: default region:center now resolves inside the zone."""
    engine = get_layout_engine()
    x, y = await _resolve_concept_position(
        position="region:center",
        group_id=None,
        is_threaded=False,
        engine=engine,
        analysis=_analysis(),
        project_id=uuid4(),
        sub_phase_id="0.0a",
    )
    assert resolve_zone_by_position(x, y, "0.0a", project_zone_bounds={}) is not None


# ---------------------------------------------------------------------------
# Phase 42 C1：1.2 接話式落點回歸（既存缺陷順帶解——threaded 預設落點不得
# 落在本關 active zone 外被 no_active_zone 硬拒；memory 2026-06 記錄）。
# ---------------------------------------------------------------------------


async def test_threaded_default_position_lands_in_pain_wall_in_1_2():
    """1.2 接話式、預設 region:center、無同群成員 → 落點必在痛點牆內。"""
    engine = get_layout_engine()
    x, y = await _resolve_concept_position(
        position="region:center",
        group_id="顧客",
        is_threaded=True,
        engine=engine,
        analysis=_analysis(),
        project_id=uuid4(),
        sub_phase_id="1.2",
    )
    zone = resolve_zone_by_position(x, y, "1.2", project_zone_bounds={})
    assert zone is not None and zone.id == "pain_wall", (x, y)


async def test_threaded_group_anchor_in_other_wall_still_snaps_to_pain_wall():
    """同群錨點在利害關係人牆（1.1c 歸群產物）→ 1.2 新痛點仍要落痛點牆，
    不可被群錨點拉去利害關係人牆觸發 zone 拒絕。"""
    engine = get_layout_engine()
    anchor = types.SimpleNamespace(
        id="n1", text="超市收銀員", x=300.0, y=300.0,  # 利害關係人牆內
        width=200.0, height=150.0, color="yellow",
        author_type="ai", created_at="", group_id=None,
        author_name="crew", kind="content", concept_group_id="顧客",
    )
    x, y = await _resolve_concept_position(
        position="region:center",
        group_id="顧客",
        is_threaded=True,
        engine=engine,
        analysis=_analysis([anchor]),
        project_id=uuid4(),
        sub_phase_id="1.2",
    )
    zone = resolve_zone_by_position(x, y, "1.2", project_zone_bounds={})
    assert zone is not None and zone.id == "pain_wall", (x, y)


async def test_threaded_second_note_clusters_near_group_inside_pain_wall():
    """同群已有痛點牆內成員 → 新便條靠群、且仍在牆內。"""
    engine = get_layout_engine()
    member = types.SimpleNamespace(
        id="p1", text="結帳才想到沒帶", x=400.0, y=1200.0,  # 痛點牆內
        width=200.0, height=150.0, color="yellow",
        author_type="ai", created_at="", group_id=None,
        author_name="crew", kind="content", concept_group_id="顧客",
    )
    x, y = await _resolve_concept_position(
        position="region:center",
        group_id="顧客",
        is_threaded=True,
        engine=engine,
        analysis=_analysis([member]),
        project_id=uuid4(),
        sub_phase_id="1.2",
    )
    zone = resolve_zone_by_position(x, y, "1.2", project_zone_bounds={})
    assert zone is not None and zone.id == "pain_wall", (x, y)
