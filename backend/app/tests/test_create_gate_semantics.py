"""Create gate 語意測試 — Phase 42 補正 R1（P0-1 section 感知＋P0-2 接受清單）。

規格依據：spec 27 v3.2 §14.8（section 帶內＝合法落點）、spec 23 v2.1 §4.1.1
（templates＝接受清單；強制只在指定 sub_phase、match 任一）。

驗證矩陣（稽核文件 §6 R1）：
  ① create 進動態 section 過閘（不再 no_active_zone）
  ② >15 字痛點便條過 1.2（不再被 problem_candidate regex 誤殺）
  ③ 2.3 根源概念自由文字過 pov_wall
  ④⑤ 準則指名判定見 test_artifact_gate.TestSelectionPairing
  ⑥ 2.2 仍強制 problem_statement（防過度放鬆回歸）
"""

from __future__ import annotations

import pytest

from app.canvas.tools_manipulation import _evaluate_create_gates

pytestmark = pytest.mark.asyncio

_PID = "00000000-0000-0000-0000-000000000000"

# RC1 帶模型預設 bounds 內的座標。
_STAKEHOLDER_XY = (200, 1700)
_PAIN_XY = (200, 2700)
_POV_XY = (200, 3800)
_CRITERIA_XY = (200, 5800)
_HMW_DOCK_XY = (200, 6400)
# 動態 section 帶（開在所有靜態帶之下）與帶內座標。
_SECTION = {"id": "sec_r1", "title": "選定區", "x": 100.0, "y": 7000.0,
            "w": 2400.0, "h": 700.0, "order": 0}
_SECTION_XY = (300, 7200)


@pytest.fixture(autouse=True)
def _mock_zone_registry(monkeypatch):
    """免 Redis：zone 用 default bounds、動態 section 預設空（個別測試再開）。"""
    async def _empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(
        "app.canvas.tools_manipulation.get_all_zones_for_project", _empty
    )
    monkeypatch.setattr("app.canvas.sections.list_sections", _no_sections)


async def _no_sections(*args, **kwargs):
    return []


async def _one_section(*args, **kwargs):
    return [dict(_SECTION)]


async def _gate(text: str, xy: tuple[int, int], sub_phase: str, *,
                kind: str = "content"):
    return await _evaluate_create_gates(
        project_id=_PID,  # type: ignore[arg-type]
        text=text,
        color="yellow",
        x=xy[0],
        y=xy[1],
        sub_phase_id=sub_phase,
        author_type="ai",
        force_publish=False,
        kind=kind,
    )


class TestSectionLanding:
    """P0-1：動態 section 帶內＝合法落點（spec 27 §14.8）。"""

    async def test_selection_reason_in_section_passes(self, monkeypatch) -> None:
        monkeypatch.setattr("app.canvas.sections.list_sections", _one_section)
        outcome = await _gate(
            "選定｜符合準則：影響範圍——最多人卡住的地方", _SECTION_XY, "2.6"
        )
        assert outcome.success is True, outcome.rejection
        assert outcome.zone_id == "section:sec_r1"

    async def test_problem_statement_in_section_passes(self, monkeypatch) -> None:
        monkeypatch.setattr("app.canvas.sections.list_sections", _one_section)
        outcome = await _gate(
            "通勤族 需要 出門不用想就帶到袋子，因為 想到時已在店裡",
            _SECTION_XY, "2.6",
        )
        assert outcome.success is True, outcome.rejection

    async def test_hmw_in_section_passes(self, monkeypatch) -> None:
        monkeypatch.setattr("app.canvas.sections.list_sections", _one_section)
        outcome = await _gate(
            "我們可以怎麼讓袋子在出門那一刻自己出現在手邊？", _SECTION_XY, "2.7"
        )
        assert outcome.success is True, outcome.rejection

    async def test_label_in_section_skips_gates(self, monkeypatch) -> None:
        monkeypatch.setattr("app.canvas.sections.list_sections", _one_section)
        outcome = await _gate("選定區", _SECTION_XY, "2.6", kind="label")
        assert outcome.success is True

    async def test_junk_in_section_rejected_with_reason_guidance(
        self, monkeypatch
    ) -> None:
        """接受清單全不中 → template_mismatch，指導語用主模板（2.6＝選定理由）。"""
        monkeypatch.setattr("app.canvas.sections.list_sections", _one_section)
        outcome = await _gate("我覺得這張不錯耶", _SECTION_XY, "2.6")
        assert outcome.success is False
        assert outcome.rejection is not None
        assert outcome.rejection.rule_name == "template_mismatch"
        assert outcome.rejection.rule_module == "template:selection_reason"

    async def test_no_section_still_no_active_zone(self) -> None:
        """帶外且無 section → 維持 no_active_zone 拒絕（不過度放鬆）。"""
        outcome = await _gate("隨便一句", _SECTION_XY, "2.6")
        assert outcome.success is False
        assert outcome.rejection is not None
        assert outcome.rejection.rule_name == "no_active_zone"


class TestAcceptedListSemantics:
    """P0-2：templates＝接受清單，強制只在指定 sub_phase（spec 23 §4.1.1）。"""

    async def test_long_pain_note_passes_1_2(self) -> None:
        """>15 字且含逗號的痛點便條不再被 problem_candidate regex 誤殺。"""
        outcome = await _gate(
            "上班族趕著出門時常常忘記帶環保袋，到店裡才想起來，只好又多拿一個塑膠袋",
            _PAIN_XY, "1.2",
        )
        assert outcome.success is True, outcome.rejection

    async def test_pain_note_free_text_passes_2_1(self) -> None:
        outcome = await _gate(
            "排隊結帳的時候才發現袋子放在機車車廂裡，回頭拿又怕位子被收走",
            _PAIN_XY, "2.1",
        )
        assert outcome.success is True, outcome.rejection

    async def test_root_cause_free_text_passes_2_3(self) -> None:
        """2.3 根源概念＝自由文字放行（舊 code 強制 problem_statement 雙句型）。"""
        outcome = await _gate(
            "根本原因是出門當下心思都在趕時間，袋子不在視線範圍就想不起來",
            _POV_XY, "2.3",
        )
        assert outcome.success is True, outcome.rejection

    async def test_2_2_still_requires_problem_statement(self) -> None:
        """回歸守衛：2.2 問題定義句型仍強制（放鬆只到 spec 允許的範圍）。"""
        outcome = await _gate("大家出門都很趕啦", _POV_XY, "2.2")
        assert outcome.success is False
        assert outcome.rejection is not None
        assert outcome.rejection.rule_name == "template_mismatch"
        assert outcome.rejection.rule_module == "template:problem_statement"

    async def test_1_1b_still_requires_stakeholder_name(self) -> None:
        """回歸守衛：利害關係人牆 1.1b 內容便條仍強制「只寫名字」模板。"""
        outcome = await _gate(
            "這是一段遠超過三十個字上限的長敘述用來確認利害關係人牆在一點一b還是只收名字不收長句",
            _STAKEHOLDER_XY, "1.1b",
        )
        assert outcome.success is False
        assert outcome.rejection is not None
        assert outcome.rejection.rule_name == "template_mismatch"

    async def test_criteria_zone_still_requires_criteria(self) -> None:
        """回歸守衛：準則區 2.5 仍強制 criteria 模板。"""
        outcome = await _gate("隨便亂寫的一張便條", _CRITERIA_XY, "2.5")
        assert outcome.success is False
        assert outcome.rejection is not None
        assert outcome.rejection.rule_name == "template_mismatch"

    async def test_criteria_zone_valid_criteria_passes(self) -> None:
        outcome = await _gate(
            "準則：影響範圍｜衡量方式：卡住人數多寡", _CRITERIA_XY, "2.5"
        )
        assert outcome.success is True, outcome.rejection

    async def test_hmw_dock_still_requires_hmw(self) -> None:
        """回歸守衛：設計題目停泊區（過渡）2.7 仍強制 hmw 句型。"""
        outcome = await _gate("就做這個吧", _HMW_DOCK_XY, "2.7")
        assert outcome.success is False
        assert outcome.rejection is not None
        assert outcome.rejection.rule_name == "template_mismatch"


class TestDedupForcePublishExemption:
    """Phase 42 補正 R4（spec 27 v3.3 §4.4）：真人 force_publish 不受貼上去重擋。"""

    async def test_ai_duplicate_rejected_human_force_publish_passes(
        self, monkeypatch
    ) -> None:
        import types as _types
        from unittest.mock import AsyncMock
        from uuid import uuid4

        from app.canvas import tools_manipulation as tm

        dup_text = "上班族趕時間常常忘記帶環保袋"
        existing = _types.SimpleNamespace(
            id="n1", text=dup_text, content=dup_text, kind="content",
            concept_group_id=None, x=200.0, y=2700.0, width=180.0, height=180.0,
            author_type="ai",
        )

        class _FakeAnalyzer:
            async def analyze(self, project_id, *, fresh: bool = False):
                return _types.SimpleNamespace(
                    notes=[existing],
                    cluster_state=_types.SimpleNamespace(clusters=[]),
                )

            async def invalidate_semantic_cache(self, project_id):
                pass

        added: list[dict] = []

        async def _add_note(project_id, **kwargs):
            added.append(kwargs)
            return "new_note_id"

        async def _gate_pass(text, modules, **kwargs):
            return _types.SimpleNamespace(
                passed=True, violated_rule=None, violated_module=None,
                matched_text=None, message_zh=None,
            )

        async def _no_color(*_a, **_k):
            return None

        monkeypatch.setattr(tm, "get_spatial_analyzer", lambda: _FakeAnalyzer())
        monkeypatch.setattr(
            tm, "canvas_ops",
            _types.SimpleNamespace(add_note=_add_note, set_note_metadata=AsyncMock()),
        )
        monkeypatch.setattr(tm, "check_text_with_llm", _gate_pass)
        monkeypatch.setattr("app.seats.colors.lookup_color_for_author", _no_color)

        pid = uuid4()
        # AI 貼重複概念 → 照常 dedup 擋。
        r_ai = await tm.tool_create_note(
            project_id=pid, text=dup_text, author_type="ai", sub_phase_id="1.2",
        )
        assert r_ai["success"] is False
        assert r_ai.get("deduped") is True

        # 真人 force_publish 同文字 → 豁免放行、真的落地。
        r_human = await tm.tool_create_note(
            project_id=pid, text=dup_text, author_type="human",
            force_publish=True, sub_phase_id="1.2",
        )
        assert r_human["success"] is True, r_human.get("rejection")
        assert len(added) == 1
