"""Tests for text templates — spec 23 v2.0（Phase 42 C2 重寫）.

現役第一鑽石模板：stakeholder / problem_statement / problem_candidate / criteria /
selection_reason / hmw（設計題目）。死模板 task_question / scope_rationale /
raw_observation / pov 已移除（pov 併入 problem_statement）。
"""

from __future__ import annotations

from app.canvas.text_templates import (
    TEMPLATES,
    get_template_prompt,
    validate_template,
)


class TestStakeholderTemplate:
    # spec 23 v2.0 §8.1：只寫名字——單行 1–30 字、禁「｜」分隔。
    def test_name_only_passes(self) -> None:
        assert validate_template("超市收銀員", "stakeholder").passed
        assert validate_template("高齡使用者", "stakeholder").passed
        assert validate_template("學生", "stakeholder").passed

    def test_old_field_format_rejected(self) -> None:
        result = validate_template(
            "宿舍管理員｜為什麼相關：最清楚哪幾間交誼廳晚上爆滿", "stakeholder"
        )
        assert not result.passed

    def test_too_long_rejected(self) -> None:
        assert not validate_template("超" * 31, "stakeholder").passed

    def test_multiline_rejected(self) -> None:
        assert not validate_template("超市收銀員\n第二行", "stakeholder").passed


class TestProblemStatementTemplate:
    # spec 23 v2.0 §2.2：需求句 OR 五要件句擇一（pov 已併入）。
    def test_need_sentence_passes(self) -> None:
        text = (
            "常騎機車買晚餐的上班族 需要 出門時不用特別想也能帶到袋子的方法，"
            "因為 他們不是不想帶，是想到的時候人已經在店裡了"
        )
        assert validate_template(text, "problem_statement").passed

    def test_five_element_sentence_passes(self) -> None:
        text = (
            "對於林阿嬤而言，在獨自準備三餐時，他/她常遇到分不清藥盒和調味料，"
            "因為視力退化但子女遠在外地，因此需要不依賴文字的辨識方式。"
        )
        assert validate_template(text, "problem_statement").passed

    def test_no_cites_line_required(self) -> None:
        # v2.0：來源關聯改 cites（系統層），便條文字不需含引用行。
        text = "電商新手 需要 在列表看到運費，因為 運費高低決定購買"
        assert validate_template(text, "problem_statement").passed

    def test_plain_text_rejected(self) -> None:
        assert not validate_template("就是想不起來帶袋子", "problem_statement").passed


class TestProblemCandidateTemplate:
    # spec 23 v2.0 §2.3：主題群標籤（2–15 字、無「｜」）。
    def test_theme_label_passes(self) -> None:
        assert validate_template("出門前就忘了帶", "problem_candidate").passed
        assert validate_template("結帳當下才想到", "problem_candidate").passed

    def test_too_long_rejected(self) -> None:
        assert not validate_template("這是一個超過十五個字的超長主題名稱不行", "problem_candidate").passed

    def test_pipe_rejected(self) -> None:
        assert not validate_template("主題｜分隔", "problem_candidate").passed


class TestCriteriaTemplate:
    def test_valid(self) -> None:
        text = "準則：時間可行性｜衡量方式：能否在 2 小時內完成"
        assert validate_template(text, "criteria").passed

    def test_missing_measure(self) -> None:
        assert not validate_template("準則：時間可行性", "criteria").passed


class TestSelectionReasonTemplate:
    # spec 23 v2.0 §2.5：「選定＋符合準則：…」。
    def test_valid(self) -> None:
        text = "選定｜符合準則：影響範圍——出門前就忘了帶是最多人卡住的地方"
        assert validate_template(text, "selection_reason").passed

    def test_missing_criterion_rejected(self) -> None:
        assert not validate_template("選定這張，感覺最重要", "selection_reason").passed


class TestHmwTemplate:
    # spec 23 v2.0 §2.4：設計題目「我們可以怎麼…？」＋禁字。
    def test_valid(self) -> None:
        assert validate_template(
            "我們可以怎麼讓袋子在出門那一刻自己出現在手邊？", "hmw"
        ).passed

    def test_old_format_rejected(self) -> None:
        # v1.0「我們如何…？\nfrom: #pov-X」格式不通過（句型 + 禁字雙擋）。
        assert not validate_template(
            "我們如何讓使用者在商品列表頁就感知到運費資訊?\nfrom: #pov-5", "hmw"
        ).passed

    def test_forbidden_terms_rejected(self) -> None:
        # 句型對但含禁字（HMW / POV / from:）→ 不通過。
        assert not validate_template("我們可以怎麼做 HMW 改寫？", "hmw").passed
        assert not validate_template("我們可以怎麼解這個 POV？", "hmw").passed
        assert not validate_template("我們可以怎麼改？ from: x", "hmw").passed

    def test_forbidden_reason_does_not_leak_rule(self) -> None:
        # #29：reason_zh 不得把禁字規則本身講出來。
        res = validate_template("我們可以怎麼做 HMW？", "hmw")
        assert not res.passed
        assert "HMW" not in (res.reason_zh or "")
        assert "禁" not in (res.reason_zh or "")


class TestRegistry:
    def test_current_templates_present(self) -> None:
        expected = {
            "stakeholder", "problem_statement", "problem_candidate",
            "criteria", "selection_reason", "hmw",
        }
        assert expected <= set(TEMPLATES.keys())

    def test_dead_templates_removed(self) -> None:
        for removed in ("task_question", "scope_rationale", "raw_observation", "pov"):
            assert removed not in TEMPLATES, f"{removed} should be removed (C2)"

    def test_no_second_diamond_templates(self) -> None:
        for removed in ("idea", "hypothesis", "task_ticket", "direction"):
            assert removed not in TEMPLATES

    def test_unknown_template_passes_through(self) -> None:
        assert validate_template("anything", "bogus").passed is True

    def test_get_template_prompt(self) -> None:
        prompt = get_template_prompt("problem_statement")
        assert prompt is not None
        assert "需要" in prompt and "因為" in prompt

    def test_empty_text_fails_known_template(self) -> None:
        assert not validate_template("", "problem_statement").passed
        assert not validate_template("  ", "stakeholder").passed
