"""Tests for content gate (Spec 13, Step 17.3)."""

from __future__ import annotations

import pytest

from app.canvas.content_gate import (
    GATE_MODULES,
    check_text,
    describe_module,
    list_gate_modules,
)


class TestNoInterpretation:
    GATE = ("no_interpretation",)

    @pytest.mark.parametrize("text", [
        "使用者真正的需求是更快結帳",
        "這代表他想要更直觀的介面",
        "我認為使用者其實是想",
        "他其實想要簡單一點",
    ])
    def test_blocked(self, text: str) -> None:
        result = check_text(text, self.GATE)
        assert result.passed is False
        assert result.violated_module == "no_interpretation"

    @pytest.mark.parametrize("text", [
        '"我都搞不清楚要按哪裡"｜情緒：焦躁',
        "受訪者 U2 停頓 5 秒後嘆氣",
        "點擊按鈕時皺眉",
    ])
    def test_passes(self, text: str) -> None:
        assert check_text(text, self.GATE).passed is True


class TestEmpathySaysNoInference:
    GATE = ("empathy_says_no_inference",)

    @pytest.mark.parametrize("text", [
        "他覺得這個介面很亂",
        "她認為應該要更簡單",
        "他應該是想找折扣",
        "他可能想要更快結帳",
    ])
    def test_blocked(self, text: str) -> None:
        assert check_text(text, self.GATE).passed is False

    @pytest.mark.parametrize("text", [
        '"我每次都找不到結帳按鈕"',
        '"運費怎麼那麼貴"',
        "U2：我每次都要重新比價",
    ])
    def test_passes(self, text: str) -> None:
        assert check_text(text, self.GATE).passed is True


class TestNoSolutionLanguage:
    GATE = ("no_solution_language",)

    @pytest.mark.parametrize("text", [
        "做一個運費試算 widget",
        "我們可以開發一個比價工具",
        "Build a comparison page",
        "增加一個快速結帳按鈕",
        "設計一個三步驟結帳",
        "我們應該蓋一個 wizard",
    ])
    def test_blocked(self, text: str) -> None:
        result = check_text(text, self.GATE)
        assert result.passed is False
        assert result.violated_module == "no_solution_language"

    @pytest.mark.parametrize("text", [
        "電商新手 需要 在不點開商品頁就看到運費，因為 運費高低決定購買意願",
        "使用者在比價時會反覆切換 tab",
        "How might we 讓運費資訊更早出現?",
    ])
    def test_passes(self, text: str) -> None:
        assert check_text(text, self.GATE).passed is True


class TestNoFeasibilityTalk:
    GATE = ("no_feasibility_talk",)

    @pytest.mark.parametrize("text", [
        "這個想法做不到啊",
        "技術上不可行",
        "成本太高",
        "我們來不及做完",
        "這個太不切實際",
    ])
    def test_blocked(self, text: str) -> None:
        assert check_text(text, self.GATE).passed is False

    @pytest.mark.parametrize("text", [
        "在商品縮圖上疊一個運費浮標｜機制：減少步驟",
        "讓 AI 預測使用者偏好｜機制：個人化",
        "做一個機器人小幫手｜機制：增加引導",  # solution-language 在 phase 3 不擋
    ])
    def test_passes(self, text: str) -> None:
        assert check_text(text, self.GATE).passed is True


class TestNoProductionCode:
    GATE = ("no_production_code",)

    @pytest.mark.parametrize("text", [
        "我們先做完整版上 production",
        "正式上線一個完整實作",
        "完整實作一個結帳流程",
    ])
    def test_blocked(self, text: str) -> None:
        assert check_text(text, self.GATE).passed is False

    @pytest.mark.parametrize("text", [
        "paper wireframe，3 個情境",
        "Figma click-through prototype",
        "role-play 模擬",
    ])
    def test_passes(self, text: str) -> None:
        assert check_text(text, self.GATE).passed is True


class TestMultiModule:
    def test_first_violation_wins(self) -> None:
        text = "我認為使用者真正想要的是 做一個快速結帳按鈕"
        result = check_text(text, ("no_interpretation", "no_solution_language"))
        assert result.passed is False
        assert result.violated_module == "no_interpretation"

    def test_no_modules_passes(self) -> None:
        result = check_text("任何東西", ())
        assert result.passed is True

    def test_unknown_module_ignored(self) -> None:
        result = check_text("使用者真正的需求是 X", ("bogus_module",))
        assert result.passed is True

    def test_empty_text_passes(self) -> None:
        assert check_text("", ("no_solution_language",)).passed is True


class TestRegistry:
    def test_all_modules_registered(self) -> None:
        expected = {
            "no_interpretation",
            "empathy_says_no_inference",
            "no_solution_language",
            "no_feasibility_talk",
            "no_production_code",
        }
        assert expected <= set(GATE_MODULES.keys())

    def test_list_modules(self) -> None:
        modules = list_gate_modules()
        assert len(modules) >= 5

    def test_describe_module_returns_chinese(self) -> None:
        desc = describe_module("no_solution_language")
        assert "解法" in desc
