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
        # A1, A2, A4, A5, A7, A8, A9, A10, A12, A13, A14, A15 = 12
        # (A3 / A6 由 content_gate 處理，不重複)
        assert len(a_triggers) >= 10

    def test_b_triggers_count(self) -> None:
        b_triggers = list_persona_triggers("B")
        # B1, B2, B3, B4, B5, B6, B7, B9, B10, B11 = 10
        assert len(b_triggers) >= 9

    def test_all_triggers_have_few_shot(self) -> None:
        for tid, spec in TRIGGERS.items():
            assert spec.few_shot, f"{tid} 缺 few_shot"
            assert spec.directive_template, f"{tid} 缺 directive_template"

    def test_critical_triggers_exist(self) -> None:
        for tid in [
            "A4_pov_count_low",
            "A5_pov_tautology",
            "A7_no_criteria_before_vote",
            "A10_category_shift_needed",
            "B1_criticism",
            "B3_time_budget_warning",
            "B6_silent_member",
            "B9_solution_language",
            "B11_advance_prompt",
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
        assert "solution-language" in SUPERVISOR_B_BASE_PROMPT

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
        inv = build_persona_prompt(
            "B",
            ["B1_criticism", "B3_time_budget_warning"],
            {
                "speaker": "Alice",
                "matched_phrase": "太蠢",
                "sub_phase": "2.2",
                "used_pct": "85",
                "remaining_pct": "15",
            },
        )
        assert "B1_criticism" in inv.interventions_block
        assert "B3_time_budget_warning" in inv.interventions_block


class TestDivergenceLabel:
    def test_divergent_phases(self) -> None:
        assert _divergence_label("1.1b") == "發散"
        assert _divergence_label("2.2") == "發散"
        assert _divergence_label("3.2") == "發散"

    def test_convergent_phases(self) -> None:
        assert _divergence_label("1.1c") == "收斂"
        assert _divergence_label("2.6") == "收斂"
        assert _divergence_label("4.2") == "收斂"


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
