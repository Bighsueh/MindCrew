"""First-diamond closing ritual contract tests（spec 26 v2.0，Phase 42 C2）.

C2：結業鏈＝痛點清單 → 問題定義 → 設計題目；選定問題定義/設計題目**直讀選定區**
（§5.3/§5.4）；payload v2 shape（§6.2，移除 stakeholders / 單數舊欄位）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.agents.first_diamond_closing import (
    _build_closing_message,
    _collect_chosen_problem_statements,
    _collect_design_questions,
    _summarize_pain_points,
    trigger_first_diamond_closing,
)
from app.agents.prompts.closing_prompts import (
    build_closing_ritual_user_prompt,
    deterministic_fallback_closing,
)
from app.canvas.zones import Bounds

pytestmark = pytest.mark.asyncio


# 選定 section bounds（動態帶；測試用固定座標）。
_SELECTION_BOUNDS = Bounds(x=100.0, y=7000.0, w=2400.0, h=700.0)
_SEL_XY = (300.0, 7200.0)

_VALID_PS = "通勤族 需要 出門時不用特別想也能帶到袋子，因為 想到時人已經在店裡了"
_VALID_REASON = "選定｜符合準則：影響範圍——最多人卡住的地方"
_VALID_HMW = "我們可以怎麼讓袋子在出門那一刻自己出現在手邊？"


@dataclass
class FakeNote:
    text: str
    x: float = 200.0
    y: float = 200.0
    kind: str = "content"
    concept_group_id: str | None = None
    id: str = ""
    cites: tuple[str, ...] = ()
    time_box_forced: bool = False
    metadata: dict | None = None


def _pain(text: str, *, group: str | None = None) -> FakeNote:
    return FakeNote(text=text, x=200.0, y=2700.0, concept_group_id=group)


def _theme_label(text: str, group: str) -> FakeNote:
    return FakeNote(text=text, x=200.0, y=2700.0, kind="label", concept_group_id=group)


def _sel_ps(note_id: str) -> FakeNote:
    return FakeNote(text=_VALID_PS, x=_SEL_XY[0], y=_SEL_XY[1], id=note_id)


def _sel_reason(note_id: str, *, cites: tuple[str, ...], forced: bool = False) -> FakeNote:
    text = "時間到了，先選這張往下走" if forced else _VALID_REASON
    return FakeNote(text=text, x=_SEL_XY[0] + 250, y=_SEL_XY[1], id=note_id,
                    cites=cites, time_box_forced=forced)


def _hmw(note_id: str, *, cites: tuple[str, ...]) -> FakeNote:
    return FakeNote(text=_VALID_HMW, x=400.0, y=5000.0, id=note_id, cites=cites)


def _patch_sections(with_section: bool = True):
    bounds_map = {"sec_test": _SELECTION_BOUNDS} if with_section else {}
    return patch(
        "app.canvas.sections.get_section_bounds_map",
        new=AsyncMock(return_value=bounds_map),
    )


# ---------------------------------------------------------------------------
# Pain point summary (unchanged from C1)
# ---------------------------------------------------------------------------


class TestSummarizePainPoints:
    async def test_empty(self) -> None:
        result = await _summarize_pain_points(uuid4(), [])
        assert result == {"total": 0, "themes": [], "highlights": []}

    async def test_totals_themes_highlights(self) -> None:
        notes = [
            _pain("結帳才想到沒帶袋子", group="t1"),
            _pain("出門前就忘了", group="t1"),
            _pain("袋子不好帶在身上", group="t2"),
            _theme_label("想起來的時機太晚", "t1"),
        ]
        result = await _summarize_pain_points(uuid4(), notes)
        assert result["total"] == 3
        assert {"label": "想起來的時機太晚", "count": 2} in result["themes"]
        assert "結帳才想到沒帶袋子" in result["highlights"]


# ---------------------------------------------------------------------------
# Selection-section direct read (spec 26 §5.3 / §5.4)
# ---------------------------------------------------------------------------


class TestCollectChosenProblemStatements:
    async def test_pairs_ps_with_reason(self) -> None:
        notes = [_sel_ps("p1"), _sel_reason("r1", cites=("p1",))]
        with _patch_sections():
            out = await _collect_chosen_problem_statements(uuid4(), notes)
        assert len(out) == 1
        assert out[0]["note_id"] == "p1"
        assert out[0]["text"] == _VALID_PS
        assert out[0]["selection_reason"] == _VALID_REASON

    async def test_forced_reason_is_none(self) -> None:
        # time_box_forced 兜底理由 → selection_reason None（§3.1 誠實，不當真實理由）。
        notes = [_sel_ps("p1"), _sel_reason("r1", cites=("p1",), forced=True)]
        with _patch_sections():
            out = await _collect_chosen_problem_statements(uuid4(), notes)
        assert out[0]["selection_reason"] is None

    async def test_real_reason_wins_over_earlier_forced(self) -> None:
        # Phase 42 補正 R4：forced 兜底先命中不得遮蔽後補真理由（修復前取第一命中即 break）。
        notes = [
            _sel_ps("p1"),
            _sel_reason("r_forced", cites=("p1",), forced=True),
            _sel_reason("r_real", cites=("p1",)),
        ]
        with _patch_sections():
            out = await _collect_chosen_problem_statements(uuid4(), notes)
        assert out[0]["selection_reason"] == _VALID_REASON

    async def test_missing_reason_is_none(self) -> None:
        notes = [_sel_ps("p1")]
        with _patch_sections():
            out = await _collect_chosen_problem_statements(uuid4(), notes)
        assert out[0]["selection_reason"] is None

    async def test_empty_selection_returns_empty(self) -> None:
        with _patch_sections(with_section=False):
            out = await _collect_chosen_problem_statements(uuid4(), [_sel_ps("p1")])
        assert out == []


class TestCollectDesignQuestions:
    def test_collects_with_valid_from(self) -> None:
        chosen = [{"note_id": "p1", "text": _VALID_PS, "selection_reason": None}]
        notes = [_hmw("h1", cites=("p1",))]
        out = _collect_design_questions(notes, chosen)
        assert len(out) == 1
        assert out[0]["from_note_id"] == "p1"
        assert out[0]["text"] == _VALID_HMW

    def test_ignores_hmw_pointing_outside_selection(self) -> None:
        chosen = [{"note_id": "p1", "text": _VALID_PS, "selection_reason": None}]
        notes = [_hmw("h1", cites=("p_other",))]  # from 指向非選定
        out = _collect_design_questions(notes, chosen)
        assert out == []

    def test_ignores_title_label_placeholder_collects_real_hmw(self) -> None:
        # WS3：組長貼的「設計題目｜我們可以怎麼…？」標題 label（cites 空）＝非交付，不收錄；
        # crew 寫的 content HMW（cites 指向選定 PS）才收錄。
        chosen = [{"note_id": "p1", "text": _VALID_PS, "selection_reason": None}]
        placeholder = FakeNote(
            text="設計題目｜我們可以怎麼…？", kind="label", id="lbl", cites=()
        )
        notes = [placeholder, _hmw("h1", cites=("p1",))]
        out = _collect_design_questions(notes, chosen)
        assert len(out) == 1
        assert out[0]["note_id"] == "h1"


# ---------------------------------------------------------------------------
# Closing prompt builders (spec 26 §3.2 / §3.3)
# ---------------------------------------------------------------------------


class TestClosingPrompts:
    def test_user_prompt_includes_chain(self) -> None:
        out = build_closing_ritual_user_prompt(
            pain_points_summary={
                "total": 6,
                "themes": [{"label": "想起來的時機太晚", "count": 3}],
                "highlights": ["結帳才想到沒帶袋子"],
            },
            chosen_problem_statements=[
                {"note_id": "p1", "text": "PS 全文", "selection_reason": "選定｜符合準則：影響範圍"},
            ],
            design_questions=[
                {"note_id": "h1", "text": "設計題目全文", "from_note_id": "p1"},
            ],
            project_name="測試專案",
        )
        assert "測試專案" in out
        assert "想起來的時機太晚" in out
        assert "PS 全文" in out
        assert "符合準則" in out
        assert "設計題目全文" in out

    def test_user_prompt_missing_reason_marked(self) -> None:
        out = build_closing_ritual_user_prompt(
            pain_points_summary={"total": 0, "themes": [], "highlights": []},
            chosen_problem_statements=[
                {"note_id": "p1", "text": "PS", "selection_reason": None},
            ],
            design_questions=[],
            project_name="X",
        )
        assert "時間內先選定" in out
        assert "還沒把設計題目定下來" in out

    def test_user_prompt_handles_empty(self) -> None:
        out = build_closing_ritual_user_prompt(
            pain_points_summary={"total": 0, "themes": [], "highlights": []},
            chosen_problem_statements=[],
            design_questions=[],
        )
        assert "暫無" in out

    def test_fallback_message_contains_design_question(self) -> None:
        out = deterministic_fallback_closing(
            design_questions=["我們可以怎麼讓袋子自己出現在手邊？"],
            pain_point_count=6,
            project_name="測試專案",
        )
        assert "我們可以怎麼讓袋子自己出現在手邊？" in out
        assert "6 張痛點" in out
        assert "測試專案" in out
        assert "推想" in out

    def test_fallback_handles_missing_design_question(self) -> None:
        out = deterministic_fallback_closing(
            design_questions=[], pain_point_count=0, project_name="",
        )
        assert "還沒把設計題目定下來" in out
        assert "發想和討論" in out

    def test_fallback_selection_reason_missing_honest(self) -> None:
        out = deterministic_fallback_closing(
            design_questions=["我們可以怎麼幫他？"],
            pain_point_count=3,
            selection_reason_missing=True,
        )
        assert "時間內選定" in out

    def test_fallback_no_english_abbreviations(self) -> None:
        out = deterministic_fallback_closing(
            design_questions=["我們可以怎麼幫他？"], pain_point_count=3,
        )
        for banned in ("HMW", "POV", "persona", "Persona"):
            assert banned not in out


# ---------------------------------------------------------------------------
# trigger_first_diamond_closing end-to-end (canvas/LLM mocked)
# ---------------------------------------------------------------------------


class TestTriggerClosing:
    async def test_returns_v2_payload(self) -> None:
        notes = [
            _pain("分不清藥盒和調味料", group="g1"),
            _sel_ps("p1"),
            _sel_reason("r1", cites=("p1",)),
            _hmw("h1", cites=("p1",)),
        ]
        fake_analysis = MagicMock(notes=notes)
        fake_analyzer = MagicMock()
        fake_analyzer.analyze = AsyncMock(return_value=fake_analysis)

        with patch(
            "app.canvas.analyzer.get_spatial_analyzer", return_value=fake_analyzer,
        ), _patch_sections(), patch(
            "app.db.session.async_session_factory"
        ) as mock_session_factory, patch(
            "app.events.bus.event_bus", MagicMock(publish=AsyncMock()),
        ), patch(
            "app.agents.first_diamond_closing._build_closing_message",
            AsyncMock(return_value="A nice closing message"),
        ):
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.get = AsyncMock(return_value=MagicMock(name="P"))

            class _CM:
                async def __aenter__(self_inner):
                    return mock_session

                async def __aexit__(self_inner, *a):
                    return False

            mock_session_factory.return_value = _CM()

            payload = await trigger_first_diamond_closing(
                uuid4(), triggered_by="ai_evaluator"
            )

        # spec 26 v2.0 §6.2 payload shape。
        assert payload["version"] == 2
        assert "stakeholders" not in payload
        assert "chosen_problem_statement" not in payload  # 單數舊欄位廢除
        assert payload["pain_points_summary"]["total"] == 1
        assert payload["chosen_problem_statements"][0]["note_id"] == "p1"
        assert payload["chosen_problem_statements"][0]["selection_reason"] == _VALID_REASON
        assert payload["design_questions"][0]["from_note_id"] == "p1"
        assert "completed_at" in payload
        assert payload["summary"] == "A nice closing message"

    async def test_canvas_failure_does_not_raise(self) -> None:
        fake_analyzer = MagicMock()
        fake_analyzer.analyze = AsyncMock(side_effect=RuntimeError("db down"))

        with patch(
            "app.canvas.analyzer.get_spatial_analyzer", return_value=fake_analyzer,
        ), _patch_sections(with_section=False), patch(
            "app.db.session.async_session_factory",
            side_effect=RuntimeError("DB down too"),
        ), patch(
            "app.events.bus.event_bus",
            MagicMock(publish=AsyncMock(side_effect=RuntimeError("chat down"))),
        ), patch(
            "app.agents.first_diamond_closing._build_closing_message",
            AsyncMock(return_value="fallback closing"),
        ):
            payload = await trigger_first_diamond_closing(
                uuid4(), triggered_by="ai_evaluator"
            )

        assert payload["version"] == 2
        assert payload["pain_points_summary"]["total"] == 0
        assert payload["chosen_problem_statements"] == []
        assert payload["design_questions"] == []
        assert payload["summary"] == "fallback closing"


# ---------------------------------------------------------------------------
# Billing attribution（Step C 回歸守衛）：閉幕 quality LLM call 的 owning_user_id
# 必須是解析出的 creator UUID、永不為 None（NOT-NULL 違反根因）。
# ---------------------------------------------------------------------------


class TestClosingBillingAttribution:
    async def test_build_closing_message_uses_resolved_owning_user(self) -> None:
        creator_id = uuid4()
        project_id = uuid4()

        fake_llm = MagicMock()
        fake_llm.chat_completion = AsyncMock(
            return_value=MagicMock(content="結業訊息")
        )

        # function-local import → patch 來源模組（非 closing 命名空間）。
        with patch(
            "app.llm.owning_user.resolve_owning_user",
            new=AsyncMock(return_value=creator_id),
        ), patch(
            "app.llm.factory.LLMProviderFactory.get_service",
            return_value=fake_llm,
        ):
            result = await _build_closing_message(
                pain_points_summary={"total": 1, "themes": [], "highlights": []},
                chosen_problem_statements=[
                    {
                        "note_id": "p1",
                        "text": _VALID_PS,
                        "selection_reason": _VALID_REASON,
                    }
                ],
                design_questions=[{"text": _VALID_HMW, "from_note_id": "p1"}],
                project_name="測試專案",
                project_id=project_id,
            )

        assert result == "結業訊息"
        fake_llm.chat_completion.assert_awaited_once()
        kwargs = fake_llm.chat_completion.await_args.kwargs
        # 核心斷言：歸屬到解析出的 creator、是 UUID、永不為 None。
        assert kwargs["owning_user_id"] == creator_id
        assert isinstance(kwargs["owning_user_id"], UUID)
        assert kwargs["owning_user_id"] is not None
        # 自主 tick：不帶 human triggered_by；project_id 照傳。
        assert kwargs.get("triggered_by_user_id") is None
        assert kwargs["project_id"] == project_id
