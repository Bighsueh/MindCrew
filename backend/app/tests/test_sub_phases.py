"""Tests for sub-phase definitions (Spec 13, Step 17.1)."""

from __future__ import annotations

import pytest

from app.stages.sub_phases import (
    COMM_MODES,
    SUB_PHASE_ORDER,
    SUB_PHASES,
    get_active_comm_mode,
    get_first_sub_phase_of_macro,
    get_next_sub_phase,
    get_sub_phase,
    get_sub_phases_of,
    has_multi_mode,
    is_sub_phase_macro_boundary,
    validate_sub_phase_advance,
)


class TestRegistryIntegrity:
    def test_all_order_entries_exist_in_registry(self) -> None:
        for sub_phase_id in SUB_PHASE_ORDER:
            assert sub_phase_id in SUB_PHASES

    def test_all_registry_entries_in_order(self) -> None:
        for sub_phase_id in SUB_PHASES:
            assert sub_phase_id in SUB_PHASE_ORDER

    def test_no_duplicate_in_order(self) -> None:
        assert len(SUB_PHASE_ORDER) == len(set(SUB_PHASE_ORDER))

    def test_expected_sub_phase_count(self) -> None:
        # Phase 1: 1.1a/b/c/d + 1.2/1.3/1.4/1.5/1.6 = 9
        # Phase 2: 2.1-2.7 = 7
        # Phase 3: 3.1-3.4 = 4
        # Phase 4: 4.1a-f + 4.1f.v2 + 4.2 + 4.3 = 9 (Spec 14 A8)
        # Total = 29
        assert len(SUB_PHASE_ORDER) == 29

    def test_all_comm_modes_are_valid(self) -> None:
        for sp in SUB_PHASES.values():
            for mode in sp.comm_modes:
                assert mode in COMM_MODES, f"{sp.id} has invalid mode {mode!r}"

    def test_all_have_at_least_one_comm_mode(self) -> None:
        for sp in SUB_PHASES.values():
            assert len(sp.comm_modes) >= 1

    def test_macro_stage_assignments(self) -> None:
        for sub_phase_id, sp in SUB_PHASES.items():
            if sub_phase_id.startswith("1."):
                assert sp.macro_stage == "discover"
            elif sub_phase_id.startswith("2."):
                assert sp.macro_stage == "define"
            elif sub_phase_id.startswith("3."):
                assert sp.macro_stage == "develop"
            elif sub_phase_id.startswith("4."):
                assert sp.macro_stage == "deliver"


class TestAdvancement:
    def test_get_next_sub_phase_normal(self) -> None:
        assert get_next_sub_phase("1.1a") == "1.1b"
        assert get_next_sub_phase("1.1d") == "1.2"
        assert get_next_sub_phase("1.6") == "2.1"
        assert get_next_sub_phase("2.7") == "3.1"

    def test_get_next_sub_phase_at_end(self) -> None:
        assert get_next_sub_phase("4.3") is None

    def test_get_next_sub_phase_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_next_sub_phase("99.9")

    def test_validate_sub_phase_advance(self) -> None:
        assert validate_sub_phase_advance("1.1a", "1.1b") is True
        assert validate_sub_phase_advance("1.1a", "1.1c") is False  # 跳級
        assert validate_sub_phase_advance("1.1d", "1.2") is True

    def test_is_macro_boundary(self) -> None:
        assert is_sub_phase_macro_boundary("1.6", "2.1") is True
        assert is_sub_phase_macro_boundary("2.7", "3.1") is True
        assert is_sub_phase_macro_boundary("1.1a", "1.1b") is False


class TestQueries:
    def test_get_sub_phase(self) -> None:
        sp = get_sub_phase("2.2")
        assert sp.id == "2.2"
        assert sp.macro_stage == "define"
        assert "no_solution_language" in sp.gate_modules

    def test_get_sub_phases_of_parent(self) -> None:
        sub_phases = get_sub_phases_of("1.1")
        ids = {sp.id for sp in sub_phases}
        assert ids == {"1.1a", "1.1b", "1.1c", "1.1d"}

    def test_get_first_sub_phase_of_macro(self) -> None:
        assert get_first_sub_phase_of_macro("discover") == "1.1a"
        assert get_first_sub_phase_of_macro("define") == "2.1"
        assert get_first_sub_phase_of_macro("develop") == "3.1"
        assert get_first_sub_phase_of_macro("deliver") == "4.1a"
        assert get_first_sub_phase_of_macro("unknown") is None


class TestCommModes:
    def test_silent_write_phases(self) -> None:
        # 1.1b stakeholder private, 1.5 raw wall, 2.2 POV, 3.2 ideas
        for sub_id in ("1.1b", "1.5", "2.2", "3.2"):
            sp = get_sub_phase(sub_id)
            assert "silent_write" in sp.comm_modes, f"{sub_id} missing silent_write"

    def test_silent_rearrange_phases(self) -> None:
        for sub_id in ("1.1c", "2.1"):
            sp = get_sub_phase(sub_id)
            assert "silent_rearrange" in sp.comm_modes

    def test_reveal_round_phases(self) -> None:
        for sub_id in ("1.1a", "1.1c", "2.2", "3.3"):
            sp = get_sub_phase(sub_id)
            assert "reveal_round" in sp.comm_modes

    def test_get_active_comm_mode_multi(self) -> None:
        # 1.1c starts in reveal_round, then silent_rearrange
        assert get_active_comm_mode("1.1c", 0) == "reveal_round"
        assert get_active_comm_mode("1.1c", 1) == "silent_rearrange"
        assert get_active_comm_mode("1.1c", 99) == "silent_rearrange"  # 越界 → 最後一個

    def test_has_multi_mode(self) -> None:
        assert has_multi_mode("1.1c") is True
        assert has_multi_mode("2.2") is True
        assert has_multi_mode("1.5") is False
        assert has_multi_mode("4.3") is False


class TestGateModules:
    def test_no_interpretation_on_raw_wall(self) -> None:
        assert "no_interpretation" in get_sub_phase("1.5").gate_modules

    def test_no_solution_language_phase_2(self) -> None:
        for sub_id in ("2.2", "2.3", "2.4", "2.5", "2.6", "2.7"):
            assert "no_solution_language" in get_sub_phase(sub_id).gate_modules

    def test_no_feasibility_talk_phase_3(self) -> None:
        for sub_id in ("3.1", "3.2", "3.3", "3.4"):
            assert "no_feasibility_talk" in get_sub_phase(sub_id).gate_modules

    def test_no_production_code_4_1f(self) -> None:
        assert "no_production_code" in get_sub_phase("4.1f").gate_modules

    def test_empathy_says_gate(self) -> None:
        assert "empathy_says_no_inference" in get_sub_phase("1.6").gate_modules


class TestZoneCoverage:
    def test_every_zoned_sub_phase_has_zones(self) -> None:
        # All sub-phases except offline (1.4) and pre-canvas should declare zones
        for sub_id in SUB_PHASE_ORDER:
            sp = get_sub_phase(sub_id)
            if sub_id == "1.4":
                continue  # offline, intentionally empty
            assert len(sp.zones) > 0, f"{sub_id} declares no zones"

    def test_empathy_map_4_quadrants_in_1_6(self) -> None:
        zones = set(get_sub_phase("1.6").zones)
        assert {"empathy_says", "empathy_thinks", "empathy_does", "empathy_feels"} <= zones

    def test_pov_wall_in_2_x(self) -> None:
        for sub_id in ("2.2", "2.3", "2.6"):
            assert "pov_wall" in get_sub_phase(sub_id).zones

    def test_idea_pool_in_3_x(self) -> None:
        for sub_id in ("3.2", "3.3", "3.4"):
            assert "idea_pool" in get_sub_phase(sub_id).zones
