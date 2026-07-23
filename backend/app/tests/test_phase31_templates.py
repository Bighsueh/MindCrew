"""Phase 31 (2026-05-26): structured template contract tests.

依據 spec/23-first-diamond-templates.md §2（§3 AI 起稿 helper 已 ARCHIVE，
Phase 42 補正 R3——對應測試同步移除）。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.canvas.text_templates import TEMPLATES, validate_template
from app.canvas.zones import ZONES, get_zone

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Persona Card 四欄位（舊 DT user persona）—— Phase 42 收尾已移除（spec 23 §2.1 歷史）
# ---------------------------------------------------------------------------


class TestPersonaCardRemoved:
    def test_persona_templates_removed_from_registry(self) -> None:
        # Phase 42 收尾（2026-06-18）：舊 DT Persona Card 四欄位模板已自 TEMPLATES
        # 移除（persona 不在 POC，spec 22 v2.0 §12.5 / spec 23 §5.1 驗收點1）。
        for tid in (
            "persona_background",
            "persona_goal",
            "persona_pain",
            "persona_implication",
        ):
            assert tid not in TEMPLATES, f"{tid} 應已移除"
            # 未知 template_id → validate_template 一律 passed=True（無 KeyError）
            assert validate_template("[林阿嬤] 背景：78 歲", tid).passed

    def test_persona_card_zone_removed(self) -> None:
        # Phase 42 C1（spec 22 v2.0 §10.10）：persona_card zone 隨 1.6 移除。
        assert "persona_card" not in ZONES


# ---------------------------------------------------------------------------
# Problem Statement 五要件 template (spec/23 §2.2)
# ---------------------------------------------------------------------------


class TestProblemStatementTemplate:
    def test_valid_full_sentence(self) -> None:
        text = (
            "對於林阿嬤而言，在獨自準備三餐時，他/她常遇到分不清藥盒和調味料，"
            "因為視力退化但子女遠在外地，因此需要不依賴文字的辨識方式。"
        )
        assert validate_template(text, "problem_statement").passed

    def test_valid_alternative_punctuation(self) -> None:
        # 半形逗號 / 不含「/」變體
        text = (
            "對於小芸而言, 在轉傳訊息時, 他她常遇到看不出真假, "
            "因為熟人轉傳信任度高, 因此需要快速查證的方法."
        )
        assert validate_template(text, "problem_statement").passed

    def test_missing_cause_fails(self) -> None:
        text = (
            "對於林阿嬤而言，在獨自準備三餐時，他/她常遇到分不清藥盒和調味料，"
            "因此需要不依賴文字的辨識方式。"
        )
        assert not validate_template(text, "problem_statement").passed

    def test_pov_wall_accepts_problem_statement_only(self) -> None:
        # Phase 42 C1：pov 模板自 2.2 zone 移除（spec 23 v2.0：併入 problem_statement；
        # regex 改寫＝批次 C2）。
        zone = get_zone("pov_wall")
        assert "problem_statement" in zone.templates
        assert "pov" not in zone.templates


# ---------------------------------------------------------------------------
# Problem candidate template (spec/23 §2.3)
# ---------------------------------------------------------------------------


class TestProblemCandidateTemplate:
    def test_valid_short(self) -> None:
        assert validate_template("分不清藥盒和調味料", "problem_candidate").passed

    def test_length_bounds(self) -> None:
        # spec 23 v2.0 §2.3：主題群標籤 2–15 字。1 字以下、含「｜」、>15 字不合格。
        assert not validate_template("短", "problem_candidate").passed
        assert not validate_template("主題｜分隔", "problem_candidate").passed
        assert not validate_template("這是一個超過十五個字的超長主題名稱絕對不行", "problem_candidate").passed

    def test_pain_wall_accepts_candidate(self) -> None:
        # Phase 42 C1：need_cluster_zone 併入痛點牆——2.1 主題群標籤貼 pain_wall。
        zone = get_zone("pain_wall")
        assert "problem_candidate" in zone.templates


# ---------------------------------------------------------------------------
# Template registry contract
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    def test_all_first_diamond_templates_registered(self) -> None:
        # Phase 42 C2 現役模板（pov 併入 problem_statement；selection_reason 新增；
        # persona_* 已於 Phase 42 收尾移除＝不在此清單）。
        for tid in (
            "stakeholder",
            "criteria",
            "hmw",
            "selection_reason",
            "problem_statement",
            "problem_candidate",
        ):
            assert tid in TEMPLATES, f"{tid} should be registered"

    def test_dead_templates_removed(self) -> None:
        # Phase 42 C2：死模板移除（pov 併入 problem_statement）；Phase 42 收尾再移除
        # persona_*（舊 DT Persona Card 四欄位，不在 POC）。
        for tid in (
            "scope_rationale",
            "raw_observation",
            "pov",
            "task_question",
            "persona_background",
            "persona_goal",
            "persona_pain",
            "persona_implication",
        ):
            assert tid not in TEMPLATES, f"{tid} should be removed"


# ---------------------------------------------------------------------------
# TemplateSuggester tests 已移除（Phase 42 補正 R3／P1-6）：模組下架標 ARCHIVE
# （無 REST 進入點），不再為封存碼維護行為測試——復活時隨 builder 重寫一併重建。
# ---------------------------------------------------------------------------
