"""Tests for sub-phase definitions（spec 22 v2.0 / 04-06 v4.25，Phase 42 C1）.

新 5＋7 格結構：0.0a → 1.1a–1.1d、1.2 → 2.1–2.7（共 13 格）。
驗收對照 spec 22 v2.0 §10（Acceptance Criteria 1–6、9、11）。
"""

from __future__ import annotations

import pytest

from app.stages.sub_phases import (
    COMM_MODES,
    SUB_PHASE_ORDER,
    SUB_PHASES,
    get_active_comm_mode,
    get_first_sub_phase_of_macro,
    get_first_sub_phase_of_micro,
    get_next_sub_phase,
    get_sub_phase,
    get_sub_phases_of,
    has_multi_mode,
    is_sub_phase_macro_boundary,
    validate_sub_phase_advance,
)


class TestRegistryIntegrity:
    def test_sub_phase_order_is_5_plus_7(self) -> None:
        # spec 22 v2.0 §10.1
        assert SUB_PHASE_ORDER == (
            "0.0a",
            "1.1a", "1.1b", "1.1c", "1.1d", "1.2",
            "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7",
        )

    def test_all_order_entries_exist_in_registry(self) -> None:
        for sub_phase_id in SUB_PHASE_ORDER:
            assert sub_phase_id in SUB_PHASES

    def test_all_registry_entries_in_order(self) -> None:
        for sub_phase_id in SUB_PHASES:
            assert sub_phase_id in SUB_PHASE_ORDER

    def test_removed_cells_absent(self) -> None:
        # spec 22 v2.0 §10.3：0.1/0.2/1.3–1.6 不在 SUB_PHASES／SUB_PHASE_ORDER。
        for removed in ("0.1", "0.2", "1.3", "1.4", "1.5", "1.6"):
            assert removed not in SUB_PHASES
            assert removed not in SUB_PHASE_ORDER

    def test_no_develop_deliver_sub_phases(self) -> None:
        """Phase 29 regression: 3.x / 4.x must not be re-introduced."""
        for sub_id in SUB_PHASE_ORDER:
            assert not sub_id.startswith("3."), f"unexpected develop sub_phase {sub_id}"
            assert not sub_id.startswith("4."), f"unexpected deliver sub_phase {sub_id}"

    def test_macro_stage_assignments(self) -> None:
        """0.0a → warmup；1.x → discover；2.x → define。"""
        for sub_phase_id, sp in SUB_PHASES.items():
            if sub_phase_id == "0.0a":
                assert sp.macro_stage == "warmup"
            elif sub_phase_id.startswith("1."):
                assert sp.macro_stage == "discover"
            elif sub_phase_id.startswith("2."):
                assert sp.macro_stage == "define"
            else:
                raise AssertionError(
                    f"unexpected macro_stage on {sub_phase_id}: {sp.macro_stage}"
                )

    def test_parent_micro_buckets(self) -> None:
        # spec 22 v2.0 §2.3a：6 桶 {0.0, 1.1, 1.2, 2.1, 2.2=2.2–2.4, 2.3=2.5–2.7}。
        expected = {
            "0.0a": "0.0",
            "1.1a": "1.1", "1.1b": "1.1", "1.1c": "1.1", "1.1d": "1.1",
            "1.2": "1.2",
            "2.1": "2.1",
            "2.2": "2.2", "2.3": "2.2", "2.4": "2.2",
            "2.5": "2.3", "2.6": "2.3", "2.7": "2.3",
        }
        for sub_id, micro in expected.items():
            assert SUB_PHASES[sub_id].parent_micro_phase == micro, sub_id

    def test_name_zh_in_scene(self) -> None:
        # spec 22 v2.0 §10.4：name_zh＝§2.3 表值；無講義標籤、無英文縮寫。
        expected = {
            "0.0a": "破冰時間｜額外用途發想",
            "1.1a": "經驗分享",
            "1.1b": "發想利害關係人",
            "1.1c": "一起歸類",
            "1.1d": "排先後順序",
            "1.2": "發想痛點與情境",
            "2.1": "痛點歸類",
            "2.2": "問題定義",
            "2.3": "追問根源",
            "2.4": "盤點現有解法",
            "2.5": "訂收斂準則",
            "2.6": "依準則挑問題定義",
            "2.7": "改寫設計題目",
        }
        for sub_id, name in expected.items():
            assert SUB_PHASES[sub_id].name_zh == name, sub_id
        for sp in SUB_PHASES.values():
            assert "講義" not in sp.name_zh
            for banned in ("HMW", "POV", "Persona", "Scope", "DEMO"):
                assert banned not in sp.name_zh, f"{sp.id} name_zh 含 {banned}"


class TestAdvancement:
    def test_get_next_sub_phase_normal(self) -> None:
        assert get_next_sub_phase("1.1a") == "1.1b"
        assert get_next_sub_phase("1.1d") == "1.2"
        # spec 22 v2.0 §11.2：macro 邊界前移——1.2 之後直接 2.1。
        assert get_next_sub_phase("1.2") == "2.1"
        # 2.7 → None（第一鑽石終局）
        assert get_next_sub_phase("2.7") is None

    def test_get_next_sub_phase_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_next_sub_phase("99.9")
        with pytest.raises(KeyError):
            get_next_sub_phase("1.5")  # 移除格＝未知 id

    def test_validate_sub_phase_advance(self) -> None:
        assert validate_sub_phase_advance("1.1a", "1.1b") is True
        assert validate_sub_phase_advance("1.1a", "1.1c") is False  # 跳級
        assert validate_sub_phase_advance("1.2", "2.1") is True

    def test_is_macro_boundary(self) -> None:
        # spec 22 v2.0 §10.11：discover→define 新邊界＝1.2 完成。
        assert is_sub_phase_macro_boundary("1.2", "2.1") is True
        assert is_sub_phase_macro_boundary("0.0a", "1.1a") is True
        assert is_sub_phase_macro_boundary("1.1a", "1.1b") is False
        assert is_sub_phase_macro_boundary("2.6", "2.7") is False


class TestQueries:
    def test_get_sub_phase(self) -> None:
        sp = get_sub_phase("2.2")
        assert sp.id == "2.2"
        assert sp.macro_stage == "define"
        assert "no_solution_language" in sp.gate_modules

    def test_get_sub_phases_of_parent(self) -> None:
        assert {sp.id for sp in get_sub_phases_of("1.1")} == {
            "1.1a", "1.1b", "1.1c", "1.1d"
        }
        assert {sp.id for sp in get_sub_phases_of("1.2")} == {"1.2"}
        assert {sp.id for sp in get_sub_phases_of("2.2")} == {"2.2", "2.3", "2.4"}
        assert {sp.id for sp in get_sub_phases_of("2.3")} == {"2.5", "2.6", "2.7"}

    def test_get_first_sub_phase_of_macro(self) -> None:
        assert get_first_sub_phase_of_macro("warmup") == "0.0a"
        assert get_first_sub_phase_of_macro("discover") == "1.1a"
        assert get_first_sub_phase_of_macro("define") == "2.1"
        assert get_first_sub_phase_of_macro("develop") is None
        assert get_first_sub_phase_of_macro("unknown") is None

    def test_get_first_sub_phase_of_micro(self) -> None:
        assert get_first_sub_phase_of_micro("1.1") == "1.1a"
        assert get_first_sub_phase_of_micro("1.2") == "1.2"
        assert get_first_sub_phase_of_micro("2.2") == "2.2"
        assert get_first_sub_phase_of_micro("2.3") == "2.5"


class TestCommModes:
    def test_comm_modes_match_spec(self) -> None:
        # spec 22 v2.0 §10.5：1.1c=reveal_round、1.2=threaded_reveal、2.2=reveal_round、
        # 2.3/2.4=threaded_reveal、其餘=discussion。
        expected = {
            "0.0a": ("discussion",),
            "1.1a": ("discussion",),
            "1.1b": ("discussion",),
            "1.1c": ("reveal_round",),
            "1.1d": ("discussion",),
            "1.2": ("threaded_reveal",),
            "2.1": ("discussion",),
            "2.2": ("reveal_round",),
            "2.3": ("threaded_reveal",),
            "2.4": ("threaded_reveal",),
            "2.5": ("discussion",),
            "2.6": ("discussion",),
            "2.7": ("discussion",),
        }
        for sub_id, modes in expected.items():
            assert SUB_PHASES[sub_id].comm_modes == modes, sub_id

    def test_phase41_silent_modes_removed(self) -> None:
        assert "silent_write" not in COMM_MODES
        assert "silent_rearrange" not in COMM_MODES
        for sp in SUB_PHASES.values():
            for mode in sp.comm_modes:
                assert mode in COMM_MODES, f"{sp.id} has invalid mode {mode!r}"

    def test_get_active_comm_mode_single(self) -> None:
        assert get_active_comm_mode("1.1c", 0) == "reveal_round"
        assert get_active_comm_mode("1.1c", 99) == "reveal_round"  # 越界 → 最後一個

    def test_has_multi_mode(self) -> None:
        for sp in SUB_PHASES.values():
            assert has_multi_mode(sp.id) is False, f"{sp.id} 非預期的多模式"


class TestGates:
    def test_min_artifact_counts_match_spec(self) -> None:
        # spec 22 v2.0 §10.6 / 25 v2.0（Phase 42 C2：2.6/2.7 特殊鍵落地）。
        assert SUB_PHASES["1.1b"].min_artifact_counts == {"stakeholder": 8}
        assert SUB_PHASES["1.2"].min_artifact_counts == {"pain_point": 6}
        assert SUB_PHASES["2.1"].min_artifact_counts == {"problem_candidate": 3}
        assert SUB_PHASES["2.2"].min_artifact_counts == {"problem_statement": 3}
        for soft in ("0.0a", "1.1a", "1.1c", "1.1d", "2.3", "2.4", "2.5"):
            assert SUB_PHASES[soft].min_artifact_counts == {}, soft
        # C2：2.6 收口閘 selection_pairing／2.7 配對閘 hmw_pairing（值=啟用旗標 1）。
        assert SUB_PHASES["2.6"].min_artifact_counts == {"selection_pairing": 1}
        assert SUB_PHASES["2.7"].min_artifact_counts == {"hmw_pairing": 1}

    def test_no_interpretation_gone(self) -> None:
        # spec 22 v2.0 §10.9：no_interpretation 全系統不存在。
        for sp in SUB_PHASES.values():
            assert "no_interpretation" not in sp.gate_modules, sp.id
            assert "empathy_says_no_inference" not in sp.gate_modules, sp.id

    def test_no_solution_language_2x_except_2_1(self) -> None:
        # spec 22 v2.0 §10.9：掛 2.2–2.7、2.1 除外。
        for sub_id in ("2.2", "2.3", "2.4", "2.5", "2.6", "2.7"):
            assert "no_solution_language" in get_sub_phase(sub_id).gate_modules, sub_id
        assert "no_solution_language" not in get_sub_phase("2.1").gate_modules

    def test_1_2_feature_jump_soft_gate(self) -> None:
        # spec 22 v2.0 §10.9：1.2「跳功能」僅軟擋（no_feature_jump，非 no_solution）。
        sp = get_sub_phase("1.2")
        assert "no_feature_jump" in sp.gate_modules
        assert "no_solution_language" not in sp.gate_modules

    def test_old_deliverables_removed(self) -> None:
        # 舊 1.1d scope_rationale 與 2.7 藍色便條 deliverable 全移除
        # （#34 便條色＝作者色；spec 25 v2.0 §2.4「配置多為空」）。
        for sp in SUB_PHASES.values():
            assert sp.deliverables_required == (), sp.id


class TestZoneCoverage:
    def test_every_sub_phase_has_zones(self) -> None:
        # 新結構無 offline／純前端格——13 格全部有牆。
        for sub_id in SUB_PHASE_ORDER:
            assert len(get_sub_phase(sub_id).zones) > 0, f"{sub_id} declares no zones"

    def test_stakeholder_wall_covers_1_1b_to_1_1d(self) -> None:
        for sub_id in ("1.1b", "1.1c", "1.1d"):
            assert "stakeholder_public" in get_sub_phase(sub_id).zones, sub_id

    def test_pain_wall_covers_1_2_and_2_1(self) -> None:
        assert get_sub_phase("1.2").zones == ("pain_wall",)
        assert get_sub_phase("2.1").zones == ("pain_wall",)

    def test_templates_no_pov(self) -> None:
        # pov 模板自 2.2 templates 移除（spec 23 v2.0：併入 problem_statement）。
        assert SUB_PHASES["2.2"].templates == ("problem_statement",)
        for sp in SUB_PHASES.values():
            assert "pov" not in sp.templates, sp.id
            assert "scope_rationale" not in sp.templates, sp.id
            assert "raw_observation" not in sp.templates, sp.id
            assert "task_question" not in sp.templates, sp.id
