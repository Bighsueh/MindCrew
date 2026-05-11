"""Tests for zone system (Spec 13, Step 17.2)."""

from __future__ import annotations

from app.canvas.zones import (
    COLORS,
    ZONES,
    Bounds,
    get_active_zones,
    get_zone,
    resolve_zone_by_position,
    zone_allows_color,
)


class TestBoundsContains:
    def test_inside(self) -> None:
        b = Bounds(0, 0, 100, 100)
        assert b.contains(50, 50) is True

    def test_on_edge(self) -> None:
        b = Bounds(0, 0, 100, 100)
        assert b.contains(100, 100) is True
        assert b.contains(0, 0) is True

    def test_outside(self) -> None:
        b = Bounds(0, 0, 100, 100)
        assert b.contains(101, 50) is False
        assert b.contains(-1, 50) is False


class TestZoneRegistry:
    def test_all_zones_have_required_fields(self) -> None:
        for zone in ZONES.values():
            assert zone.id
            assert len(zone.allowed_colors) >= 1
            assert all(c in COLORS for c in zone.allowed_colors)

    def test_park_zone_removed(self) -> None:
        """Phase 21：Park（孤兒區）已移除。"""
        assert "park" not in ZONES

    def test_get_zone(self) -> None:
        z = get_zone("pov_wall")
        assert z.id == "pov_wall"
        assert "no_solution_language" in z.gate_modules


class TestActiveZones:
    def test_1_6_has_empathy_quadrants(self) -> None:
        active_ids = {z.id for z in get_active_zones("1.6")}
        assert {"empathy_says", "empathy_thinks", "empathy_does", "empathy_feels"} <= active_ids

    def test_2_2_has_pov_wall(self) -> None:
        active_ids = {z.id for z in get_active_zones("2.2")}
        assert "pov_wall" in active_ids

    def test_3_2_has_idea_pool(self) -> None:
        active_ids = {z.id for z in get_active_zones("3.2")}
        assert "idea_pool" in active_ids

    def test_unknown_sub_phase_returns_empty(self) -> None:
        """Phase 21：Park 已移除，未知 sub_phase 無 active zone。"""
        assert get_active_zones("99.9") == []


class TestColorRules:
    def test_define_criteria_only_green(self) -> None:
        z = get_zone("define_criteria_sidebar")
        assert z.allowed_colors == ("green",)
        assert zone_allows_color(z, "green") is True
        assert zone_allows_color(z, "yellow") is False

    def test_hmw_dock_blue_and_pink(self) -> None:
        z = get_zone("hmw_dock")
        assert "blue" in z.allowed_colors
        assert "pink" in z.allowed_colors

    def test_raw_wall_yellow_only(self) -> None:
        z = get_zone("raw_wall")
        assert z.allowed_colors == ("yellow",)


class TestResolveByPosition:
    def test_resolve_pov_wall(self) -> None:
        # pov_wall default x=100..2100 y=100..1300
        z = resolve_zone_by_position(500, 500, "2.2")
        assert z is not None
        assert z.id == "pov_wall"

    def test_resolve_outside_any_zone(self) -> None:
        # 遠離所有 zone
        z = resolve_zone_by_position(99999, 99999, "2.2")
        assert z is None

    def test_resolve_outside_for_inactive_phase(self) -> None:
        """Phase 21：Park 已移除，1.1a 的 (2450, 100) 不再落在任何 zone。"""
        z = resolve_zone_by_position(2450, 100, "1.1a")
        assert z is None

    def test_resolve_with_project_override(self) -> None:
        # 自訂 bounds 覆寫 default
        override = {"pov_wall": Bounds(x=5000, y=5000, w=100, h=100)}
        z = resolve_zone_by_position(5050, 5050, "2.2", project_zone_bounds=override)
        assert z is not None
        assert z.id == "pov_wall"
