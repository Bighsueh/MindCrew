"""Phase 32 (2026-05-26): Supervisor tool_status awareness contract tests.

依據 spec/24-supervisor-tool-awareness.md §2-§3。

Phase 42 收尾（2026-06-18）：舊 DT 「user persona」（Persona Card 四欄位、1.6
sub_phase）已不在 POC、相關 helper 自 code 移除——本檔的 persona 測試（aggregation／
format block／classify persona／contract persona_fields）已隨之刪除；只保留現行的
問題定義（2.2）／設計題目（2.7）工具感知測試。
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.tool_status import (
    TOOL_STATUS_SUB_PHASES,
    _aggregate_hmw_status,
    _aggregate_ps_status,
    _classify_sticky,
    _format_hmw_block,
    _format_ps_block,
    serialize_tool_status,
)

pytestmark = pytest.mark.asyncio


@dataclass
class FakeNote:
    text: str


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class TestClassifySticky:
    def test_problem_statement(self) -> None:
        text = (
            "對於林阿嬤而言，在獨自準備三餐時，他/她常遇到分不清藥盒，"
            "因為視力退化，因此需要不依賴文字的辨識方式。"
        )
        tid, name = _classify_sticky(text)
        assert tid == "problem_statement"
        assert name == "林阿嬤"

    def test_unknown(self) -> None:
        tid, name = _classify_sticky("這只是一張普通便條紙")
        assert tid is None
        assert name is None


# ---------------------------------------------------------------------------
# Aggregators
# ---------------------------------------------------------------------------


class TestPSAggregation:
    def test_zero(self) -> None:
        assert _aggregate_ps_status([]) == 0

    def test_count_three(self) -> None:
        ps = (
            "對於林阿嬤而言，在獨自準備三餐時，他/她常遇到分不清藥盒，"
            "因為視力退化，因此需要不依賴文字的辨識方式。"
        )
        notes = [FakeNote(text=ps), FakeNote(text=ps), FakeNote(text=ps)]
        assert _aggregate_ps_status(notes) == 3


class TestHMWAggregation:
    def test_zero(self) -> None:
        assert _aggregate_hmw_status([]) == 0

    def test_count(self) -> None:
        # Phase 42 C2：設計題目「我們可以怎麼…？」（spec 23 v2.0 §2.4）。
        hmw = "我們可以怎麼讓使用者在列表頁看到運費？"
        notes = [FakeNote(text=hmw), FakeNote(text=hmw)]
        assert _aggregate_hmw_status(notes) == 2


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class TestFormatters:
    def test_ps_block_zero_suggests_structure(self) -> None:
        out = _format_ps_block(0)
        assert "尚未產出任何問題定義" in out
        assert "structure" in out

    def test_ps_block_below_threshold(self) -> None:
        out = _format_ps_block(1)
        assert "1/3" in out

    def test_ps_block_threshold_met_suggests_selection(self) -> None:
        # Phase 42 C2：無投票收斂——改建議開選定區（spec 27 §14）。
        out = _format_ps_block(4)
        assert "選定區" in out
        assert "無投票" in out
        assert "voting" not in out

    def test_hmw_block_zero_suggests_creativity(self) -> None:
        out = _format_hmw_block(0)
        assert "尚未產出任何設計題目" in out
        assert "creativity" in out

    def test_hmw_block_count_no_voting(self) -> None:
        out = _format_hmw_block(3)
        assert "3 句" in out
        assert "voting" not in out and "投票" not in out


# ---------------------------------------------------------------------------
# serialize_tool_status (end-to-end with mocked analyzer)
# ---------------------------------------------------------------------------


class TestSerializeToolStatus:
    async def test_non_tool_sub_phase_returns_empty(self) -> None:
        # 1.1a is NOT a tool_status sub_phase
        out = await serialize_tool_status(uuid4(), "1.1a")
        assert out == ""

    async def test_unknown_sub_phase_returns_empty(self) -> None:
        out = await serialize_tool_status(uuid4(), None)
        assert out == ""

    async def test_removed_1_6_returns_empty(self) -> None:
        # Phase 42：1.6（舊 DT Persona）已移除、不在 TOOL_STATUS_SUB_PHASES。
        out = await serialize_tool_status(uuid4(), "1.6")
        assert out == ""

    async def test_2_2_renders_ps_block(self) -> None:
        ps_text = (
            "對於林阿嬤而言，在獨自準備三餐時，他/她常遇到分不清藥盒，"
            "因為視力退化，因此需要不依賴文字的辨識方式。"
        )
        notes = [FakeNote(text=ps_text)]
        fake_analysis = MagicMock(notes=notes)
        fake_analyzer = MagicMock()
        fake_analyzer.analyze = AsyncMock(return_value=fake_analysis)

        with patch(
            "app.canvas.analyzer.get_spatial_analyzer",
            return_value=fake_analyzer,
        ):
            out = await serialize_tool_status(uuid4(), "2.2")

        assert "問題定義狀態" in out

    async def test_2_7_renders_hmw_block(self) -> None:
        hmw = "我們可以怎麼讓使用者在列表頁看到運費？"
        notes = [FakeNote(text=hmw)]
        fake_analysis = MagicMock(notes=notes)
        fake_analyzer = MagicMock()
        fake_analyzer.analyze = AsyncMock(return_value=fake_analysis)

        with patch(
            "app.canvas.analyzer.get_spatial_analyzer",
            return_value=fake_analyzer,
        ):
            out = await serialize_tool_status(uuid4(), "2.7")

        assert "設計題目狀態" in out

    async def test_analyzer_failure_returns_empty(self) -> None:
        fake_analyzer = MagicMock()
        fake_analyzer.analyze = AsyncMock(side_effect=RuntimeError("db down"))

        with patch(
            "app.canvas.analyzer.get_spatial_analyzer",
            return_value=fake_analyzer,
        ):
            # 2.2 is a live tool sub_phase → goes through analyzer (which raises).
            out = await serialize_tool_status(uuid4(), "2.2")

        # No exception bubbled — graceful degradation
        assert out == ""


# ---------------------------------------------------------------------------
# Module-level contracts
# ---------------------------------------------------------------------------


class TestContract:
    def test_tool_status_sub_phases_correct(self) -> None:
        # Phase 42 D4：1.6（Persona）已移除、不在 POC；現行＝問題定義 2.2／設計題目 2.7。
        assert TOOL_STATUS_SUB_PHASES == {"2.2", "2.7"}

    def test_old_dt_persona_symbols_removed(self) -> None:
        # Phase 42 收尾：舊 DT persona helper 已自 tool_status 移除（回歸守衛）。
        import app.agents.tool_status as ts

        for sym in (
            "PERSONA_FIELDS",
            "FIELD_TO_RECOMMENDED_LENS",
            "_aggregate_persona_status",
            "_format_persona_block",
            "_extract_persona_name",
            "_empty_persona_record",
        ):
            assert not hasattr(ts, sym), f"{sym} 應已移除"
