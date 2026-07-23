"""Tests for supervisor A/B personas + router (Phase 18 Stream C)."""

from __future__ import annotations

import pytest

from app.agents.supervisor.personas import (
    SUPERVISOR_A_BASE_PROMPT,
    SUPERVISOR_B_BASE_PROMPT,
    TRIGGERS,
    build_persona_prompt,
    get_trigger,
    list_persona_triggers,
)
from app.agents.supervisor.triggers_a import _divergence_label
from app.agents.supervisor.triggers_b import _latest_non_supervisor_message


class TestTriggerRegistry:
    def test_a_triggers_count(self) -> None:
        a_triggers = list_persona_triggers("A")
        # Phase 29 移除第二鑽石（commit 0e9b464）時，A10/A12-A15 等隨之刪除；
        # A3/A6 由 content_gate 處理（不重複）；Phase 42 C1：A2 隨舊 1.1d
        # （scope 收斂）整格抽換移除。現存第一鑽石 A-trigger：
        # A1, A4, A5, A9 = 4（與 triggers_a.py 實際 fire 集合一致）。
        # Phase 42 C2：A7（criteria-before-vote）/A8（too many winners）隨投票機制移除——
        # 「挑前先有準則」由選定理由模板（必指準則）承載、「選定 ≤3」由 selection_pairing
        # 收口閘 enforce（spec 25 §3.2）。
        assert len(a_triggers) == 4

    def test_b_triggers_count(self) -> None:
        b_triggers = list_persona_triggers("B")
        # Phase 41：B7_peek_in_silent_write 已移除（沉默模式取消）。
        # Phase 42：advance-prompt trigger 已廢除（spec/16 §4.6，職能併入組長常態推進迴路）；
        # B2 新增 B12_off_topic_redirect（spec 15 v2.0 §2.3.1）。
        # 現存 B1, B2, B3(a/b/c/critical), B4, B5, B6, B9, B12 = 9 組
        assert len(b_triggers) >= 9

    def test_all_triggers_have_few_shot(self) -> None:
        for tid, spec in TRIGGERS.items():
            assert spec.few_shot, f"{tid} 缺 few_shot"
            assert spec.directive_template, f"{tid} 缺 directive_template"

    def test_critical_triggers_exist(self) -> None:
        # Phase 17 timer pressure: B3 was split into B3a / B3b / B3c / B3_critical
        # (see spec/16-timer-system §6.5). Test asserts one of the variants exists.
        # Phase 29：A10_category_shift_needed 隨第二鑽石移除（親和圖換類別已不獨立成 trigger）。
        for tid in [
            "A4_pov_count_low",
            "A5_pov_tautology",
            "A9_hmw_not_written",
            "B1_criticism",
            "B3a_halfway_pivot",
            "B6_silent_member",
            "B9_solution_language",
            "B12_off_topic_redirect",
        ]:
            assert get_trigger(tid) is not None, f"{tid} missing"


class TestPromptAssembly:
    def test_persona_a_base_contains_key_phrases(self) -> None:
        assert "問題解決" in SUPERVISOR_A_BASE_PROMPT
        assert "發散" in SUPERVISOR_A_BASE_PROMPT
        assert "收斂" in SUPERVISOR_A_BASE_PROMPT

    def test_persona_b_base_contains_key_phrases(self) -> None:
        assert "合作紀律" in SUPERVISOR_B_BASE_PROMPT
        assert "批評" in SUPERVISOR_B_BASE_PROMPT
        # Phase 42 B2（spec 15 §5 條 6 大白話）：「solution-language」英文殘留已改中文。
        assert "解法" in SUPERVISOR_B_BASE_PROMPT
        assert "solution-language" not in SUPERVISOR_B_BASE_PROMPT

    def test_tone_baseline_in_both_bases(self) -> None:
        # Spec 15 §2.1.1（v2.0）：語氣基準 A/B 共用——沉穩有興致、無 emoji、hedging。
        for base in (SUPERVISOR_A_BASE_PROMPT, SUPERVISOR_B_BASE_PROMPT):
            assert "沉穩有興致" in base
            assert "不得出現 emoji" in base
            assert "我猜" in base  # hedging 語氣詞
            assert "權力距離" in base

    def test_no_voting_residue_anywhere(self) -> None:
        # Spec 15 v2.0 §2.3：全程無投票——prompt 不得出現投票話術（b4 廢除）。
        assert "投票" not in SUPERVISOR_A_BASE_PROMPT
        assert "投票" not in SUPERVISOR_B_BASE_PROMPT
        for tid, spec in TRIGGERS.items():
            assert "投票" not in spec.few_shot, f"{tid} few_shot 含投票殘留"
            assert "投票" not in spec.directive_template, f"{tid} directive 含投票殘留"
            assert "投票" not in spec.description_zh, f"{tid} description 含投票殘留"

    def test_no_english_jargon_in_few_shots(self) -> None:
        # Spec 15 §5 條 6（#17/#25）：對學員的範例語句禁英文縮寫／行話。
        banned = ("POV", "HMW", "re-scope", "fidelity", "solution-language", "INSIGHT")
        for tid, spec in TRIGGERS.items():
            for term in banned:
                assert term not in spec.few_shot, f"{tid} few_shot 含「{term}」"

    def test_b12_off_topic_redirect_content(self) -> None:
        # Spec 15 v2.0 §2.3.1：答完收束＋主動拉回兩型。
        spec = get_trigger("B12_off_topic_redirect")
        assert spec is not None
        assert spec.persona == "B"
        assert "回來" in spec.few_shot  # 答完收束回任務
        assert "正常回答" in spec.directive_template
        assert "拉回" in spec.directive_template

    def test_b1_criticism_new_wording(self) -> None:
        # Spec 15 v2.0 §2.3.2：制止話術改新語氣（低權力距離、轉成可用材料）。
        spec = get_trigger("B1_criticism")
        assert spec is not None
        assert "每個想法都先留著" in spec.few_shot
        assert "寶貴" in spec.directive_template

    def test_build_persona_prompt_a4(self) -> None:
        inv = build_persona_prompt(
            "A", ["A4_pov_count_low"], {"count": "1", "needed": "2"},
        )
        assert inv.persona == "A"
        assert "問題解決" in inv.base_prompt
        assert "A4_pov_count_low" in inv.interventions_block
        # Context substituted into few-shot
        assert "1" in inv.interventions_block or "2" in inv.interventions_block

    def test_build_persona_prompt_b1(self) -> None:
        inv = build_persona_prompt(
            "B", ["B1_criticism"], {"speaker": "Alice", "matched_phrase": "太蠢"},
        )
        assert inv.persona == "B"
        assert "Alice" in inv.interventions_block
        assert "太蠢" in inv.interventions_block

    def test_build_persona_prompt_multi_triggers(self) -> None:
        # Phase 17 timer pressure split B3 into B3a; this test uses the
        # halfway_pivot variant which still represents time-budget pressure.
        inv = build_persona_prompt(
            "B",
            ["B1_criticism", "B3a_halfway_pivot"],
            {
                "speaker": "Alice",
                "matched_phrase": "太蠢",
                "sub_phase": "2.2",
                "used_pct": "55",
                "remaining_pct": "45",
            },
        )
        assert "B1_criticism" in inv.interventions_block
        assert "B3a_halfway_pivot" in inv.interventions_block


class TestDivergenceLabel:
    def test_divergent_phases(self) -> None:
        # Phase 29 (spec/04-06 §4.10): 3.x sub-phases removed.
        assert _divergence_label("1.1b") == "發散"
        assert _divergence_label("2.2") == "發散"

    def test_convergent_phases(self) -> None:
        # Phase 42 C1：1.1c/1.1d 改 divergent（spec 16 v2.0 §6.5.2——1.x 全程
        # 發散側；矛盾裁定見 phase_intent.py 註）；收斂＝2.1/2.5/2.6/2.7。
        assert _divergence_label("1.1c") == "發散"
        assert _divergence_label("2.1") == "收斂"
        assert _divergence_label("2.6") == "收斂"
        assert _divergence_label("2.7") == "收斂"


class TestLatestNonSupervisorMessage:
    def test_skips_supervisor(self) -> None:
        chat = [
            {"sender": "Alice", "content": "hi"},
            {"sender": "supervisor", "content": "歡迎"},
        ]
        result = _latest_non_supervisor_message(chat)
        assert result is not None
        assert result["sender"] == "Alice"

    def test_skips_supervisor_display_name(self) -> None:
        chat = [
            {"sender": "Alice", "content": "hi"},
            {"sender": "AI 引導者", "content": "我來了"},
        ]
        result = _latest_non_supervisor_message(chat)
        assert result is not None
        assert result["sender"] == "Alice"

    def test_returns_none_if_all_supervisor(self) -> None:
        chat = [{"sender": "supervisor", "content": "x"}]
        assert _latest_non_supervisor_message(chat) is None
