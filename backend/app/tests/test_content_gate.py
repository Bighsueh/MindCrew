"""Tests for content gate (Spec 13, Step 17.3)."""

from __future__ import annotations

import pytest

from app.canvas.content_gate import (
    GATE_MODULES,
    check_text,
    describe_module,
    list_gate_modules,
)


class TestRemovedModules:
    """Phase 42 C1（spec 04-06 v4.25 §5.5）：no_interpretation／
    empathy_says_no_inference 隨舊 1.5/1.6 全系統移除——未知 module 安靜略過。"""

    def test_modules_unregistered(self) -> None:
        assert "no_interpretation" not in GATE_MODULES
        assert "empathy_says_no_inference" not in GATE_MODULES

    def test_legacy_module_ids_pass_through(self) -> None:
        # 殘留呼叫端帶舊 module id → 視為未知、不擋（與既有未知 module 行為一致）。
        assert check_text("使用者真正的需求是更快結帳", ("no_interpretation",)).passed
        assert check_text("他覺得這個介面很亂", ("empathy_says_no_inference",)).passed


class TestNoFeatureJump:
    """Phase 42 C1（spec 04-06 v4.25 §5.5）：1.2「跳到功能」提醒＋軟擋。"""

    GATE = ("no_feature_jump",)

    @pytest.mark.parametrize("text", [
        "他需要一個提醒功能",
        "他需要一個 App 幫他記",
        "做一個小程式提醒他",
        "幫他加一個通知",
    ])
    def test_blocked(self, text: str) -> None:
        result = check_text(text, self.GATE)
        assert result.passed is False
        assert result.violated_module == "no_feature_jump"
        # 軟擋話術＝內容層大白話（#29）：不講 gate/規則名。
        assert "gate" not in (result.message_zh or "")

    @pytest.mark.parametrize("text", [
        "結帳那一刻才想起袋子放在家裡",
        "店員已經開始裝塑膠袋了，他來不及開口",
        "出門前趕著上班，腦子裡只有會議",
    ])
    def test_situations_pass(self, text: str) -> None:
        # 描述具體情境與卡點的正常句子不該誤中（窄關鍵字表）。
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
        text = "先不評估可行性 做一個快速結帳按鈕"
        result = check_text(text, ("no_feature_jump", "no_solution_language"))
        assert result.passed is False
        assert result.violated_module == "no_feature_jump"

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
            "no_solution_language",
            "no_feature_jump",
            "no_feasibility_talk",
            "no_production_code",
            "no_criticism",
            "must_be_concept",
        }
        assert expected <= set(GATE_MODULES.keys())

    def test_list_modules(self) -> None:
        modules = list_gate_modules()
        assert len(modules) >= 5

    def test_describe_module_returns_chinese(self) -> None:
        desc = describe_module("no_solution_language")
        assert "解法" in desc


class TestTier2Override:
    """check_text_with_llm 的 LLM 二判 override 契約（Phase 42 補正 R2／P1-8）。

    修復前零整合測試＋裸吞錯＋「LLM 判斷：」機制詞直達學生 RejectToast。
    """

    @staticmethod
    def _judge(verdict: str, confidence: float = 0.9):
        from app.agents.llm_judge import JudgeResult

        return JudgeResult(
            verdict=verdict,  # type: ignore[arg-type]
            confidence=confidence,
            reasoning_zh="這句是在引述別人說過的話，不是自己提解法",
            rule_module="no_solution_language",
        )

    @pytest.mark.asyncio
    async def test_llm_disagrees_overrides_regex_to_pass(self, monkeypatch) -> None:
        from app.canvas.content_gate import check_text_with_llm

        async def _fake_judge(**kwargs):
            return self._judge("pass")

        monkeypatch.setattr("app.agents.llm_judge.judge_content", _fake_judge)
        result = await check_text_with_llm("做一個 APP 解決它", ("no_solution_language",))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_llm_agrees_keeps_reject_no_mechanism_words(self, monkeypatch) -> None:
        from app.canvas.content_gate import check_text_with_llm

        async def _fake_judge(**kwargs):
            return self._judge("violate")

        monkeypatch.setattr("app.agents.llm_judge.judge_content", _fake_judge)
        result = await check_text_with_llm("做一個 APP 解決它", ("no_solution_language",))
        assert result.passed is False
        # #29：學生可見文字不得出現「LLM 判斷」機制詞；補充理由仍在。
        assert "LLM" not in (result.message_zh or "")
        assert "補充說明" in (result.message_zh or "")

    @pytest.mark.asyncio
    async def test_llm_agrees_low_confidence_passes(self, monkeypatch) -> None:
        # is_violating 嚴格判定：信心不足不擋。
        from app.canvas.content_gate import check_text_with_llm

        async def _fake_judge(**kwargs):
            return self._judge("violate", confidence=0.3)

        monkeypatch.setattr("app.agents.llm_judge.judge_content", _fake_judge)
        result = await check_text_with_llm("做一個 APP 解決它", ("no_solution_language",))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_llm_failure_conservative_pass_with_warning(
        self, monkeypatch, caplog
    ) -> None:
        import logging

        from app.canvas.content_gate import check_text_with_llm

        async def _boom(**kwargs):
            raise RuntimeError("provider down")

        monkeypatch.setattr("app.agents.llm_judge.judge_content", _boom)
        with caplog.at_level(logging.WARNING, logger="app.canvas.content_gate"):
            result = await check_text_with_llm(
                "做一個 APP 解決它", ("no_solution_language",)
            )
        assert result.passed is True
        # P1-8：吞錯不再隱形——必須留 WARNING。
        assert any("tier-2" in rec.message for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_regex_clean_never_calls_llm(self, monkeypatch) -> None:
        from app.canvas.content_gate import check_text_with_llm

        called = {"n": 0}

        async def _fake_judge(**kwargs):
            called["n"] += 1
            return self._judge("pass")

        monkeypatch.setattr("app.agents.llm_judge.judge_content", _fake_judge)
        result = await check_text_with_llm(
            "使用者常常忘記帶袋子", ("no_solution_language",)
        )
        assert result.passed is True
        assert called["n"] == 0
