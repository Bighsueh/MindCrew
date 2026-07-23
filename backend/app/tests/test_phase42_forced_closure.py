"""2.6 time-box 強制收口測試（spec 16 v2.0 §4.3 / 04-06 §5.8，Phase 42 C2）.

內容層安全閥：time-box 到而選定區不滿足收口閘時，系統挑最有共識的 1 張問題定義搬進
選定區、自動補一張 time_box_forced 選定理由，保證 2.7 配對閘永遠有合法輸入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.progression.forced_closure import force_close_selection

pytestmark = pytest.mark.asyncio

_PS_TEXT = "通勤族 需要 出門時不用特別想也能帶到袋子，因為 想到時人已經在店裡了"
_SECTION = {"id": "sec1", "title": "選定區", "x": 100.0, "y": 3000.0, "w": 2400.0, "h": 700.0, "order": 1}


@dataclass
class FakeNote:
    text: str
    x: float = 200.0
    y: float = 2000.0   # 預設落在選定區帶外（pov_wall 區）
    kind: str = "content"
    concept_group_id: str | None = None
    id: str = ""
    cites: tuple[str, ...] = ()
    time_box_forced: bool = False
    metadata: dict = field(default_factory=dict)


def _gate_result(passed: bool):
    r = MagicMock()
    r.passed = passed
    return r


def _run_ctx(notes, *, gate_passed=False, sections=None, pre_members=None,
             post_members=None, move_ok=True):
    """組合所有 patch：gate、analyzer、sections、canvas_ops。回 (ctx, canvas_ops_mock)。

    selection_members 以 side_effect 控制「搬動前（line 68）／搬動後重讀（_confirm）」兩次
    回傳：``pre_members`` 預設空（候選 PS 在帶外）→ 觸發搬入路徑；``post_members`` 預設空
    （模擬搬動沒落地 → _confirm 回 False）。happy path 傳 post_members=[被選 PS]。
    ``move_ok`` 控制 batch_update_coordinates 回傳（False＝sidecar 拒絕）。
    """
    fake_analysis = MagicMock(notes=notes)
    fake_analyzer = MagicMock(analyze=AsyncMock(return_value=fake_analysis))
    canvas_ops_mock = MagicMock(
        batch_update_coordinates=AsyncMock(return_value=move_ok),
        add_note=AsyncMock(return_value="forced_reason_id"),
    )
    secs = sections if sections is not None else [_SECTION]
    pre = pre_members if pre_members is not None else []
    post = post_members if post_members is not None else []
    sel_mock = AsyncMock(side_effect=[pre, post, post, post, post])
    patches = [
        patch("app.canvas.artifact_gate.check_artifact_gate",
              new=AsyncMock(return_value=_gate_result(gate_passed))),
        patch("app.canvas.analyzer.get_spatial_analyzer", return_value=fake_analyzer),
        patch("app.canvas.sections.list_sections", new=AsyncMock(return_value=secs)),
        # selection_members（gate wrapper 與 _confirm 共用此單一真理源）。
        patch("app.canvas.sections.selection_members", new=sel_mock),
        patch("app.bridge.canvas_ops.canvas_ops", canvas_ops_mock),
    ]
    return patches, canvas_ops_mock


class TestForceCloseSelection:
    async def test_gate_already_satisfied_noop(self) -> None:
        patches, ops = _run_ctx([], gate_passed=True)
        for p in patches:
            p.start()
        try:
            acted = await force_close_selection(uuid4())
        finally:
            for p in patches:
                p.stop()
        assert acted is False
        ops.batch_update_coordinates.assert_not_called()
        ops.add_note.assert_not_called()

    async def test_picks_most_cited_ps_and_adds_forced_reason(self) -> None:
        ps_high = FakeNote(text=_PS_TEXT, id="ps_high", cites=("pain1", "pain2", "pain3"))
        notes = [
            FakeNote(text=_PS_TEXT, id="ps_low", cites=("pain1",)),
            ps_high,
        ]
        # 搬動後重讀確認 ps_high 已落進選定區（_confirm_in_selection 通過）。
        patches, ops = _run_ctx(notes, post_members=[ps_high])
        for p in patches:
            p.start()
        try:
            acted = await force_close_selection(uuid4())
        finally:
            for p in patches:
                p.stop()
        assert acted is True
        # 搬最有共識（cites 最多）的 ps_high 進選定區。
        mv = ops.batch_update_coordinates.call_args
        moved = mv.args[1] if len(mv.args) > 1 else mv.kwargs["updates"]
        assert moved[0]["id"] == "ps_high"
        # 補一張 time_box_forced 理由、cites 指向被選的 ps_high。
        kw = ops.add_note.call_args.kwargs
        assert kw["time_box_forced"] is True
        assert kw["cites"] == ["ps_high"]

    async def test_move_rejected_returns_false_no_false_claim(self) -> None:
        # WS2a：batch_update_coordinates 回 False（sidecar 找不到便條）→ 不謊報選好、不補理由。
        ps = FakeNote(text=_PS_TEXT, id="ps1", cites=("pain1", "pain2"))
        patches, ops = _run_ctx([ps], move_ok=False)
        for p in patches:
            p.start()
        try:
            acted = await force_close_selection(uuid4())
        finally:
            for p in patches:
                p.stop()
        assert acted is False
        ops.add_note.assert_not_called()

    async def test_move_not_in_selection_after_move_returns_false(self) -> None:
        # WS2a：搬動「成功」但重讀發現 PS 不在選定區（雙 section／沒持久化）→ 誠實回 False。
        ps = FakeNote(text=_PS_TEXT, id="ps1", cites=("pain1", "pain2"))
        patches, ops = _run_ctx([ps], move_ok=True, post_members=[])  # 重讀看不到 → 不在區
        for p in patches:
            p.start()
        try:
            acted = await force_close_selection(uuid4())
        finally:
            for p in patches:
                p.stop()
        assert acted is False
        ops.add_note.assert_not_called()

    async def test_no_candidates_returns_false(self) -> None:
        patches, ops = _run_ctx([FakeNote(text="不是問題定義的雜訊", id="x")])
        for p in patches:
            p.start()
        try:
            acted = await force_close_selection(uuid4())
        finally:
            for p in patches:
                p.stop()
        assert acted is False
        ops.batch_update_coordinates.assert_not_called()


class TestSelectionSectionIdempotency:
    """WS1：選定 section 冪等（spec 10 §5.9）——同標題不重開，避免雙選定區。"""

    async def test_open_section_reuses_existing_same_title(self) -> None:
        from app.canvas.tools_zones import tool_open_section

        existing = {
            "id": "sec_existing", "title": "選定區｜要往下做的問題",
            "x": 100.0, "y": 2000.0, "w": 2400.0, "h": 700.0, "order": 1,
        }
        conv = MagicMock()
        conv.convert = lambda t: t  # 繞過 OpenCC、標題直接比對
        reg = AsyncMock()
        comp = AsyncMock()
        patches = [
            patch("app.canvas.tools_zones.chinese_converter", conv),
            patch("app.canvas.sections.list_sections", new=AsyncMock(return_value=[existing])),
            patch("app.canvas.sections.register_section", new=reg),
            patch("app.canvas.sections.compute_open_section_bounds", new=comp),
            patch("app.bridge.canvas_ops.canvas_ops", MagicMock(add_note=AsyncMock())),
        ]
        for p in patches:
            p.start()
        try:
            res = await tool_open_section(
                uuid4(), title="選定區｜要往下做的問題", author_id="agent_supervisor"
            )
        finally:
            for p in patches:
                p.stop()
        assert res["section_id"] == "sec_existing"
        assert res.get("reused") is True
        reg.assert_not_called()   # 不再 mint 新 section
        comp.assert_not_called()  # 不再往下算新帶

    async def test_forced_offsets_within_section_band(self) -> None:
        # WS1/WS2a 寫者(force_close 搬入點)與讀者(selection_members 帶內)對齊：
        # 強制搬入的相對落點必須落在 section 帶 (w×h) 內。
        from app.progression.forced_closure import _FORCED_PS_OFFSET, _FORCED_REASON_OFFSET
        from app.canvas.sections import SECTION_BAND_WIDTH, SECTION_BAND_HEIGHT

        for ox, oy in (_FORCED_PS_OFFSET, _FORCED_REASON_OFFSET):
            assert 0.0 <= ox <= SECTION_BAND_WIDTH
            assert 0.0 <= oy <= SECTION_BAND_HEIGHT
