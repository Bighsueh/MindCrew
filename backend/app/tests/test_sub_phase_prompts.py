"""Tests for sub_phase_prompts 分角色注入＋13 關進場語（spec 04-03 v4.25 §3，Phase 42 B2）。"""

from __future__ import annotations

import re

import pytest

from app.agents.prompts import sub_phase_entry, sub_phase_prompts
from app.agents.prompts.sub_phase_entry import (
    SUB_PHASE_CREW_POINTS,
    SUB_PHASE_ENTRY,
    SUPERVISOR_COMMON_RULES,
    TEACHING_GUIDE,
)
from app.agents.prompts.sub_phase_prompts import (
    SUB_PHASE_OBJECTIVES,
    build_sub_phase_prompt,
)

# 新 13 關（0.0a 進場語由 warmup_game 承載，不在 ENTRY）
_NEW_GRID = ["0.0a", "1.1a", "1.1b", "1.1c", "1.1d", "1.2",
             "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7"]
_ENTRY_GRID = [g for g in _NEW_GRID if g != "0.0a"]


@pytest.mark.unit
class TestEntryData:
    def test_entry_covers_12_grids_not_warmup(self) -> None:
        assert set(SUB_PHASE_ENTRY.keys()) == set(_ENTRY_GRID)
        assert set(SUB_PHASE_CREW_POINTS.keys()) == set(_ENTRY_GRID)

    def test_objectives_cover_new_grid(self) -> None:
        for g in _NEW_GRID:
            assert g in SUB_PHASE_OBJECTIVES, f"{g} 缺 objective"

    def test_fixed_label_texts(self) -> None:
        # Spec 04-03 §3.x：標題便條固定文案（逐字）。macro 必貼 3 張＋各關標題。
        expectations = {
            "1.1a": ["發現階段｜把問題打開、先不做決定", "經驗分享｜聊聊自己的真實經驗"],
            "1.1b": ["利害關係人｜這件事會影響到誰"],
            "1.1c": ["一起歸類｜相似的放一起"],
            "1.1d": ["排先後順序｜先挖誰、後挖誰"],
            "1.2": ["痛點牆｜誰在什麼情況卡住了"],
            "2.1": ["定義階段｜把問題收成一句設計題目", "痛點歸類｜同一件事的放一起"],
            "2.2": ["問題定義｜誰需要什麼、為什麼"],
            "2.3": ["追問根源｜多問幾次為什麼"],
            "2.4": ["現有解法｜市面上已經有什麼"],
            "2.5": ["準則｜用什麼尺來挑"],
            "2.6": ["選定區｜要往下做的問題"],
            "2.7": ["設計題目｜我們可以怎麼…？"],
        }
        for grid, labels in expectations.items():
            for label in labels:
                assert label in SUB_PHASE_ENTRY[grid], f"{grid} 缺標題文案「{label}」"

    def test_canonical_phrases(self) -> None:
        # 關鍵 canonical 話術抽查（spec §3.x 固定句型）。
        assert "先留著，現在不刪人" in SUB_PHASE_ENTRY["1.1d"]  # 防偷收斂
        assert "先回到他卡住的那個當下" in SUB_PHASE_ENTRY["1.2"]  # 跳到功能軟擋
        assert "這兩件記得都做喔，我在旁邊看著" in SUB_PHASE_ENTRY["2.1"]  # 雙要求提醒非命令
        assert "某使用者 需要 某需求，因為 某洞察" in SUB_PHASE_ENTRY["2.2"]
        assert "時間差不多了，我來收一下" in SUB_PHASE_ENTRY["2.6"]  # 時間安全閥
        assert "選定＋符合準則" in SUB_PHASE_ENTRY["2.6"]
        assert "我們可以怎麼" in SUB_PHASE_ENTRY["2.7"]

    def test_demo_before_ask_grids(self) -> None:
        # #26：2.1／2.6 要求 crew 先示範搬移。
        assert "示範" in SUB_PHASE_ENTRY["2.1"]
        assert "示範" in SUB_PHASE_ENTRY["2.6"]
        assert "示範" in SUB_PHASE_CREW_POINTS["2.1"]
        assert "示範" in SUB_PHASE_CREW_POINTS["2.6"]

    def test_supervisor_common_rules_content(self) -> None:
        # Spec 04-03 §3.0.1：九段守則的關鍵段落。
        for fragment in ("【語氣】", "【名詞】", "【點名與推進】", "【任務提示】",
                         "【不代貼】", "【不講內部】", "【答離題】", "【不批評】", "【卡住就教】"):
            assert fragment in SUPERVISOR_COMMON_RULES, f"§3.0.1 缺 {fragment}"


@pytest.mark.unit
class TestRoleSplit:
    def test_supervisor_gets_rules_and_entry(self) -> None:
        out = build_sub_phase_prompt("1.1b", role="supervisor")
        assert SUPERVISOR_COMMON_RULES in out
        assert "組長進場" in out
        assert "利害關係人｜這件事會影響到誰" in out

    def test_teaching_guide_injected_for_supervisor(self) -> None:
        # 04-03 §3.0.3：【卡住就教】引用的教學三段式模板必須有落點（不可懸空）。
        for fragment in ("【教學三段式】", "給選擇優於空白創作", "明確動作",
                         "打『可以』兩個字"):
            assert fragment in TEACHING_GUIDE
        out = build_sub_phase_prompt("2.5", role="supervisor")
        assert TEACHING_GUIDE in out
        assert TEACHING_GUIDE not in build_sub_phase_prompt("2.5", role="crew")

    def test_entry_placeholders_are_interpolatable(self) -> None:
        # 進場語點名佔位符必須用 interpolation 層認得的形式（@{顯示名}/@{crew_name}），
        # 組裝時帶真名；不可用「@（真人顯示名）」這種插不到值的舞台指示。
        from app.agents.prompts.interpolation import (
            interpolate_crew_names,
            interpolate_human_name,
        )
        seats = [
            {"role": "crew_1", "type": "ai", "display_name": "陳秀英"},
            {"role": "human_creator", "type": "human", "user_name": "小明"},
        ]
        for k, text in SUB_PHASE_ENTRY.items():
            assert "（真人顯示名）" not in text, f"ENTRY[{k}] 殘留舞台指示佔位符"
            assert "（指派一位隊友顯示名）" not in text, f"ENTRY[{k}] 殘留舞台指示佔位符"
            out = interpolate_human_name(interpolate_crew_names(text, seats), seats)
            assert "@{顯示名}" not in out, f"ENTRY[{k}] 佔位符未被插值"
            assert "{crew_name}" not in out, f"ENTRY[{k}] 佔位符未被插值"

    def test_crew_gets_points_not_entry(self) -> None:
        out = build_sub_phase_prompt("1.1b", role="crew")
        assert SUPERVISOR_COMMON_RULES not in out
        assert "組長進場" not in out
        assert "隊友）怎麼做" in out
        assert "只寫名字" in out

    def test_default_role_is_crew(self) -> None:
        assert build_sub_phase_prompt("2.2") == build_sub_phase_prompt("2.2", role="crew")

    def test_warmup_not_duplicated(self) -> None:
        # 0.0a 進場語由 warmup_game 承載——此處兩個角色都不該有進場語/示範段。
        for role in ("supervisor", "crew"):
            out = build_sub_phase_prompt("0.0a", role=role)
            assert "組長進場" not in out
            assert "破冰時間" in out  # objective 仍在

    def test_legacy_grid_does_not_crash(self) -> None:
        # Phase 42 C1：舊結構格已自 registry 移除——未知 id 安靜回空字串、不炸。
        out = build_sub_phase_prompt("1.3", role="supervisor")
        assert out == ""
        assert "組長進場" not in out

    def test_unknown_grid_returns_empty(self) -> None:
        assert build_sub_phase_prompt("9.9", role="supervisor") == ""

    def test_supervisor_only_tool_line(self) -> None:
        sup = build_sub_phase_prompt("2.2", role="supervisor")
        crew = build_sub_phase_prompt("2.2", role="crew")
        assert "draw_zone" in sup
        assert "draw_zone" not in crew


@pytest.mark.unit
class TestHygiene:
    _EMOJI = re.compile(
        "[\U0001F000-\U0001FAFF☀-➿⬀-⯿✅❌✓✗⭐⚠]"
    )

    def test_no_emoji_in_module_constants(self) -> None:
        # Phase 42 B2：第三層 prompt 全面禁 emoji（含 ✓✗ 等符號標記）。
        for name, text in [
            ("SUPERVISOR_COMMON_RULES", SUPERVISOR_COMMON_RULES),
            *[(f"ENTRY[{k}]", v) for k, v in SUB_PHASE_ENTRY.items()],
            *[(f"CREW[{k}]", v) for k, v in SUB_PHASE_CREW_POINTS.items()],
            *[(f"OBJ[{k}]", v) for k, v in SUB_PHASE_OBJECTIVES.items()],
            *[(f"COMM[{k}]", v) for k, v in sub_phase_prompts.COMM_MODE_DESCRIPTIONS.items()],
        ]:
            hit = self._EMOJI.search(text)
            assert hit is None, f"{name} 含 emoji/符號 {hit.group()!r}"

    def test_no_student_facing_english_jargon_in_entries(self) -> None:
        # Spec 15 §5 條 6：進場語/crew 要點禁英文縮寫（HMW/POV 等）。
        banned = ("HMW", "POV", "Define", "Discover", "Warmup", "Persona")
        for k in _ENTRY_GRID:
            for term in banned:
                assert term not in SUB_PHASE_ENTRY[k], f"ENTRY[{k}] 含「{term}」"
                assert term not in SUB_PHASE_CREW_POINTS[k], f"CREW[{k}] 含「{term}」"


@pytest.mark.unit
class TestShareInviteEntry:
    """Phase 42（1.1a 隊友沉默修復）：1.1a 進場改為「逐一邀請」腳本。"""

    def test_1_1a_entry_invites_one_at_a_time(self) -> None:
        entry = SUB_PHASE_ENTRY["1.1a"]
        assert "一次只邀一位" in entry
        assert "set_directive" in entry
        assert "每一位隊友都要輪到一次" in entry

    def test_1_1a_entry_keeps_human_placeholder(self) -> None:
        # 仍要 @ 邀真人——interpolate_human_name 靠 {顯示名} placeholder。
        assert "{顯示名}" in SUB_PHASE_ENTRY["1.1a"]

    def test_1_1a_entry_keeps_completion_signal(self) -> None:
        assert "每位隊友接過至少一段自身經驗" in SUB_PHASE_ENTRY["1.1a"]
