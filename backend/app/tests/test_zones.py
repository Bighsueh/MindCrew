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
    def test_removed_zones_absent(self) -> None:
        """Phase 42 C1（spec 22 v2.0 §10.10 / 23 v2.0 §4.2）：隨格移除的 zone 不存在。"""
        for removed in (
            "task_clarification_zone", "stakeholder_private", "scope_zone",
            "division_zone", "interview_strategy_zone", "raw_wall",
            "empathy_says", "empathy_thinks", "empathy_does", "empathy_feels",
            "persona_card", "journey_map", "need_cluster_zone",
        ):
            assert removed not in ZONES, removed

    def test_stakeholder_wall_active_1_1b_to_1_1d(self) -> None:
        for sub_id in ("1.1b", "1.1c", "1.1d"):
            active_ids = {z.id for z in get_active_zones(sub_id)}
            assert "stakeholder_public" in active_ids, sub_id

    def test_pain_wall_active_1_2_and_2_1(self) -> None:
        for sub_id in ("1.2", "2.1"):
            active_ids = {z.id for z in get_active_zones(sub_id)}
            assert "pain_wall" in active_ids, sub_id

    def test_2_2_has_pov_wall(self) -> None:
        active_ids = {z.id for z in get_active_zones("2.2")}
        assert "pov_wall" in active_ids

    def test_idea_pool_zone_removed(self) -> None:
        """Phase 29 (spec/04-06 §4.10): idea_pool zone removed with second diamond."""
        assert "idea_pool" not in ZONES
        # 3.2 sub-phase itself is also removed
        assert get_active_zones("3.2") == []

    def test_unknown_sub_phase_returns_empty(self) -> None:
        """Phase 21：Park 已移除，未知 sub_phase 無 active zone。"""
        assert get_active_zones("99.9") == []

    def test_zone_titles_empty_no_english_leak(self) -> None:
        """Phase 42 C1（#13/#25）：框標題全留空——視覺錨點＝組長標題便條；
        消掉舊標題英文外漏（POV/HMW/Define）。"""
        for zone in ZONES.values():
            if zone.visual is not None:
                assert zone.visual.title_sticky == "", zone.id


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

    def test_pain_wall_colors(self) -> None:
        z = get_zone("pain_wall")
        assert "yellow" in z.allowed_colors


class TestResolveByPosition:
    def test_resolve_pov_wall(self) -> None:
        # RC1 帶模型：pov_wall default 帶 x=100..2100 y=3660..4860
        z = resolve_zone_by_position(500, 3800, "2.2")
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
