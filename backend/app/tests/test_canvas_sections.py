"""動態 section（open_section）測試 — Phase 42 C0，spec 10 v2.0 §2.3/§5.9。

涵蓋：
1. 「往下開新帶」bounds 硬計算（空白板 / zone extent / 便條 extent / 既有 section）
2. registry 註冊 round-trip（真 Redis，隨機 project id）
3. tool_open_section：標題便條 kind=label、過 OpenCC、回 section_id
4. supervisor-only：非組長呼叫 open_section 被擋
5. layout engine `section:<id>` 帶內落點與避撞
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.canvas import sections as sections_mod
from app.canvas.layout_engine import LayoutEngine
from app.canvas.sections import (
    SECTION_BAND_HEIGHT,
    SECTION_BAND_WIDTH,
    SECTION_GAP,
    SECTION_START_X,
    clear_project_sections,
    compute_open_section_bounds,
    get_section_bounds_map,
    list_sections,
    register_section,
    resolve_section_by_position,
)
from app.canvas.spatial import NOTE_HEIGHT, NOTE_WIDTH, SpatialNote
from app.canvas.zones import Bounds


def _note(id: str, x: float, y: float) -> SpatialNote:
    return SpatialNote(
        id=id, text="t", x=x, y=y,
        width=NOTE_WIDTH, height=NOTE_HEIGHT,
        color="yellow", author_type="ai", created_at="",
    )


@pytest.fixture
def _no_zones_no_notes(monkeypatch):
    async def _empty_zones(project_id):
        return {}

    async def _no_shapes(self, project_id):
        return []

    monkeypatch.setattr(sections_mod, "get_all_zones_for_project", _empty_zones)
    from app.bridge.canvas_ops import CanvasOps

    monkeypatch.setattr(CanvasOps, "get_canvas_state_full", _no_shapes)


@pytest.mark.asyncio
class TestComputeBounds:
    async def test_empty_board_starts_at_top(self, _no_zones_no_notes) -> None:
        bounds, order = await compute_open_section_bounds(uuid4())
        assert bounds.y == 100.0
        assert bounds.x == SECTION_START_X
        assert bounds.w == SECTION_BAND_WIDTH
        assert bounds.h == SECTION_BAND_HEIGHT
        assert order == 1

    async def test_below_lowest_zone(self, monkeypatch, _no_zones_no_notes) -> None:
        async def _zones(project_id):
            return {"raw_wall": Bounds(x=100, y=100, w=2200, h=1200)}

        monkeypatch.setattr(sections_mod, "get_all_zones_for_project", _zones)
        bounds, _ = await compute_open_section_bounds(uuid4())
        assert bounds.y == 100 + 1200 + SECTION_GAP

    async def test_below_lowest_note(self, monkeypatch, _no_zones_no_notes) -> None:
        async def _shapes(self, project_id):
            return [{"id": "n1", "x": 200, "y": 2000, "height": 150}]

        from app.bridge.canvas_ops import CanvasOps

        monkeypatch.setattr(CanvasOps, "get_canvas_state_full", _shapes)
        bounds, _ = await compute_open_section_bounds(uuid4())
        assert bounds.y == 2000 + 150 + SECTION_GAP


@pytest.mark.asyncio
class TestRegistry:
    async def test_register_roundtrip_and_order(self, _no_zones_no_notes) -> None:
        project_id = uuid4()
        try:
            b1, o1 = await compute_open_section_bounds(project_id)
            s1 = await register_section(project_id, "選定區", b1, o1)
            assert s1["id"].startswith("sec_")

            listed = await list_sections(project_id)
            assert [s["id"] for s in listed] == [s1["id"]]
            assert listed[0]["title"] == "選定區"

            # 第二條帶開在第一條之下、order 遞增
            b2, o2 = await compute_open_section_bounds(project_id)
            assert b2.y >= b1.y + b1.h + SECTION_GAP
            assert o2 == o1 + 1

            bounds_map = await get_section_bounds_map(project_id)
            assert s1["id"] in bounds_map
            assert bounds_map[s1["id"]].y == b1.y

            # containment 反推（move-delta 區名用）
            hit = resolve_section_by_position(listed, b1.x + 10, b1.y + 10)
            assert hit is not None and hit["id"] == s1["id"]
            assert resolve_section_by_position(listed, b1.x + 10, b1.y - 50) is None
        finally:
            await clear_project_sections(project_id)


@pytest.mark.asyncio
class TestToolOpenSection:
    async def test_creates_label_title_note(self, monkeypatch, _no_zones_no_notes) -> None:
        from app.bridge.canvas_ops import CanvasOps
        from app.canvas.tools_zones import tool_open_section

        captured: dict = {}

        async def _fake_add_note(self, project_id, content, **kwargs):
            captured["content"] = content
            captured["kind"] = kwargs.get("kind")
            captured["position"] = kwargs.get("position")
            return "shape:note_label_1"

        monkeypatch.setattr(CanvasOps, "add_note", _fake_add_note)

        project_id = uuid4()
        try:
            result = await tool_open_section(
                project_id, "選定區", author_id="supervisor", author_name="組長",
            )
            assert result["success"] is True
            assert result["section_id"].startswith("sec_")
            assert result["title_note_id"] == "shape:note_label_1"
            # 標題便條：kind=label、貼在帶頭
            assert captured["kind"] == "label"
            assert captured["content"] == "選定區"
            assert captured["position"]["y"] == result["bounds"]["y"] + 8
        finally:
            await clear_project_sections(project_id)

    async def test_empty_title_rejected(self) -> None:
        from app.canvas.tools_zones import tool_open_section

        result = await tool_open_section(uuid4(), "  ")
        assert result["success"] is False


@pytest.mark.asyncio
class TestSupervisorOnly:
    async def test_crew_blocked(self) -> None:
        from app.agents.act_canvas import execute_canvas_tool

        result = await execute_canvas_tool(
            "open_section",
            {"title": "選定區"},
            project_id=uuid4(),
            agent_id="crew_a",
            agent_name="小明",
            seat_role="crew_a",
        )
        assert result == {"success": False, "error": "supervisor_only"}

    async def test_wired_into_action_tables(self) -> None:
        from app.agents.act import _NON_SUBSTANTIVE_ROUND_TYPES, _SUPERVISOR_ONLY_ACTIONS
        from app.agents.act_canvas import CANVAS_ACTION_TYPES, SUPERVISOR_ONLY_ACTIONS
        from app.agents.think import _VALID_ACTION_TYPES

        assert "open_section" in _VALID_ACTION_TYPES
        assert "open_section" in _SUPERVISOR_ONLY_ACTIONS
        assert "open_section" in _NON_SUBSTANTIVE_ROUND_TYPES
        assert "open_section" in CANVAS_ACTION_TYPES
        assert "open_section" in SUPERVISOR_ONLY_ACTIONS


class TestSectionPlacement:
    def test_place_within_band_and_avoid_collision(self) -> None:
        engine = LayoutEngine()
        band = Bounds(x=100, y=3000, w=2400, h=700)
        sections = {"sec_a": band}

        x1, y1 = engine.resolve_position(
            "section:sec_a", notes=[], sections=sections,
        )
        # 帶內（x 範圍）、且在標題帶之下
        assert band.x <= x1 <= band.x + band.w - NOTE_WIDTH
        assert y1 >= band.y + NOTE_HEIGHT

        # 第二張避開第一張
        occupied = [_note("n1", x1, y1)]
        x2, y2 = engine.resolve_position(
            "section:sec_a", notes=occupied, sections=sections,
        )
        assert (x2, y2) != (x1, y1)
        assert not (
            x2 < x1 + NOTE_WIDTH and x2 + NOTE_WIDTH > x1
            and y2 < y1 + NOTE_HEIGHT and y2 + NOTE_HEIGHT > y1
        )

    def test_unknown_section_falls_back(self) -> None:
        engine = LayoutEngine()
        # sections 無此 id → fallback organic 落點（不丟例外）
        x, y = engine.resolve_position("section:sec_missing", notes=[], sections={})
        assert isinstance(x, float) and isinstance(y, float)
