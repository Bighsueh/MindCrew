"""Tests for text templates (Spec 13, Step 17.3)."""

from __future__ import annotations

import pytest

from app.canvas.text_templates import (
    TEMPLATES,
    get_template_prompt,
    list_templates,
    validate_template,
)


class TestStakeholderTemplate:
    def test_valid(self) -> None:
        result = validate_template("高齡使用者｜佐證：訪談-3", "stakeholder")
        assert result.passed

    def test_missing_evidence(self) -> None:
        result = validate_template("高齡使用者", "stakeholder")
        assert not result.passed


class TestRawObservationTemplate:
    def test_valid(self) -> None:
        text = '"我都搞不清楚"｜情緒：焦躁｜來源：U2'
        assert validate_template(text, "raw_observation").passed

    def test_missing_quote(self) -> None:
        text = "我都搞不清楚｜情緒：焦躁｜來源：U2"
        assert not validate_template(text, "raw_observation").passed


class TestPovTemplate:
    def test_valid(self) -> None:
        text = (
            "電商新手 需要 在列表看到運費，因為 運費高低決定購買\n"
            "cites: #obs-1, #obs-2"
        )
        assert validate_template(text, "pov").passed

    def test_missing_cites(self) -> None:
        text = "電商新手 需要 看到運費，因為 影響購買"
        assert not validate_template(text, "pov").passed

    def test_missing_because(self) -> None:
        text = "電商新手 需要 看到運費\ncites: #obs-1"
        assert not validate_template(text, "pov").passed


class TestHmwTemplate:
    def test_valid_english(self) -> None:
        text = "How might we let users see shipping early?\nfrom: #pov-1"
        assert validate_template(text, "hmw").passed

    def test_valid_chinese(self) -> None:
        text = "我們如何讓使用者在列表頁看到運費?\nfrom: #pov-3"
        assert validate_template(text, "hmw").passed

    def test_missing_from(self) -> None:
        text = "我們如何讓使用者更快結帳?"
        assert not validate_template(text, "hmw").passed


class TestCriteriaTemplate:
    def test_valid(self) -> None:
        text = "準則：時間可行性｜衡量方式：能否在 2 小時內完成"
        assert validate_template(text, "criteria").passed

    def test_missing_measure(self) -> None:
        assert not validate_template("準則：時間可行性", "criteria").passed


class TestIdeaTemplate:
    def test_valid(self) -> None:
        text = "縮圖上疊運費標籤｜機制：減少步驟\nfor: #hmw-A"
        assert validate_template(text, "idea").passed

    def test_missing_for(self) -> None:
        text = "縮圖上疊運費標籤｜機制：減少步驟"
        assert not validate_template(text, "idea").passed


class TestHypothesisTemplate:
    def test_valid(self) -> None:
        text = "假設：顯示運費會提高加購率｜成功：+15%｜失敗：無差異｜min_fidelity：wireframe"
        assert validate_template(text, "hypothesis").passed

    def test_missing_field(self) -> None:
        text = "假設：顯示運費會提高加購率｜成功：+15%"
        assert not validate_template(text, "hypothesis").passed


class TestTaskTicketTemplate:
    def test_valid(self) -> None:
        text = (
            "任務：商品列表 wireframe｜驗收：3 個情境可演示｜fidelity 上限：wireframe\n"
            "hypothesis: #hyp-1"
        )
        assert validate_template(text, "task_ticket").passed

    def test_missing_hypothesis_ref(self) -> None:
        text = "任務：商品列表 wireframe｜驗收：3 個情境｜fidelity 上限：wireframe"
        assert not validate_template(text, "task_ticket").passed


class TestDirectionTemplate:
    @pytest.mark.parametrize("choice", ["close", "loop_define", "loop_develop"])
    def test_valid(self, choice: str) -> None:
        text = f"決定：{choice}\n理由：經過 debrief 確認"
        assert validate_template(text, "direction").passed

    def test_invalid_choice(self) -> None:
        text = "決定：something_else\n理由：x"
        assert not validate_template(text, "direction").passed


class TestRegistry:
    def test_all_required_templates(self) -> None:
        expected = {
            "stakeholder", "scope_rationale", "raw_observation",
            "pov", "criteria", "hmw", "idea",
            "hypothesis", "task_ticket", "direction",
        }
        assert expected <= set(TEMPLATES.keys())

    def test_unknown_template_passes_through(self) -> None:
        result = validate_template("anything", "bogus")
        assert result.passed is True

    def test_get_template_prompt(self) -> None:
        prompt = get_template_prompt("pov")
        assert prompt is not None
        assert "需要" in prompt and "因為" in prompt

    def test_empty_text_fails_known_template(self) -> None:
        assert not validate_template("", "pov").passed
        assert not validate_template("  ", "stakeholder").passed
