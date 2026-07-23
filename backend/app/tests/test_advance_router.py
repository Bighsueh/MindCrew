"""三層推進路由（Phase 42 A1，progression/advance_router.py）。

對現行 SUB_PHASE_ORDER（C1 重構前）驗證 resolve_advance_target 的位置判定，
與 execute_advance_target 的 gate 前置檢查／分派。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.progression import advance_router as ar


class TestResolveAdvanceTarget:
    def test_mid_micro_cell_resolves_to_sub(self) -> None:
        t = ar.resolve_advance_target("1.1a")
        assert t.kind == "sub"
        assert t.to_sub_phase == "1.1b"

    def test_last_cell_of_micro_resolves_to_micro(self) -> None:
        # 1.1d 是 micro 1.1 末格；下一 micro 1.2 同屬 discover。
        t = ar.resolve_advance_target("1.1d")
        assert t.kind == "micro"
        assert t.from_micro == "1.1"
        assert t.to_micro == "1.2"

    def test_macro_boundary_resolves_to_stage(self) -> None:
        # Phase 42 C1：1.2 是 micro 1.2 末格；1.2→2.1 跨 discover→define
        # （spec 22 v2.0 §2.4 macro 邊界前移）。
        t = ar.resolve_advance_target("1.2")
        assert t.kind == "stage"
        assert t.from_stage == "discover"

    def test_terminal_resolves_to_stage(self) -> None:
        # 2.7 是終局 micro 2.3 末格（define→completed，觸發結業鏈）。
        t = ar.resolve_advance_target("2.7")
        assert t.kind == "stage"
        assert t.from_stage == "define"

    def test_unknown_cell_resolves_to_none(self) -> None:
        assert ar.resolve_advance_target("9.9z").kind == "none"


@pytest.mark.asyncio
async def test_execute_sub_delegates_with_announce_flag() -> None:
    pid = uuid4()
    target = ar.resolve_advance_target("1.1a")
    with patch(
        "app.agents.stage_advancement.advance_sub_phase",
        new=AsyncMock(return_value="sub_advanced_to_1.1b"),
    ) as adv:
        result = await ar.execute_advance_target(
            project_id=pid, agent_id="supervisor", target=target,
            skip_gate_check=False, announce=False,
        )
    assert result == "sub_advanced_to_1.1b"
    kwargs = adv.call_args.kwargs
    assert kwargs["skip_deliverable_check"] is False
    assert kwargs["announce"] is False


@pytest.mark.asyncio
async def test_execute_completed_room_silently_noop() -> None:
    """P1-9（Phase 42 補正 R4）：completed 終態 guard——不分派、不產生 blocked 話術。

    修復前 supervisor 迴圈無停止條件，completed 後仍反覆 advance→gate 擋→
    rejection 話術（LLM 空轉實證燒 ~1.5h）。回值無 sub_advance_blocked 前綴
    → act 層 rejection=None 靜默。"""
    pid = uuid4()
    target = ar.resolve_advance_target("2.7")

    class _FakeSession:
        async def scalar(self, *_a, **_k):
            return "completed"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    with (
        patch("app.db.session.async_session_factory", new=lambda: _FakeSession()),
        patch("app.agents.stage_advancement.advance_stage", new=AsyncMock()) as adv,
        patch.object(ar, "human_gate_blocks", new=AsyncMock()) as hg,
    ):
        result = await ar.execute_advance_target(
            project_id=pid, agent_id="supervisor", target=target,
        )
    assert result == "advance_noop:completed_terminal"
    adv.assert_not_awaited()
    hg.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_micro_blocked_by_gate_precheck() -> None:
    """micro 跨界在 gate 未過時被擋（advance_micro_phase 本身無 gate，由 router 補）。"""
    pid = uuid4()
    target = ar.resolve_advance_target("1.1d")
    with (
        patch.object(
            ar, "gates_pass_with_reason",
            new=AsyncMock(return_value=(False, "「利害關係人」便條目前 3 張、需要 8 張")),
        ),
        patch(
            "app.agents.stage_advancement.advance_micro_phase", new=AsyncMock()
        ) as adv,
    ):
        result = await ar.execute_advance_target(
            project_id=pid, agent_id="supervisor", target=target,
        )
    assert result.startswith("sub_advance_blocked:artifact_gate:")
    adv.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_micro_skip_gate_bypasses_precheck() -> None:
    """time-box 誠實收尾（skip_gate_check=True）→ 不做 gate 前置檢查直接跨。"""
    pid = uuid4()
    target = ar.resolve_advance_target("1.1d")
    with (
        patch.object(ar, "gates_pass_with_reason", new=AsyncMock()) as gate,
        patch(
            "app.agents.stage_advancement.advance_micro_phase",
            new=AsyncMock(return_value="micro_advanced_to_1.2"),
        ),
    ):
        result = await ar.execute_advance_target(
            project_id=pid, agent_id="system_progression", target=target,
            skip_gate_check=True, announce=False,
        )
    assert result == "micro_advanced_to_1.2"
    gate.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_stage_passes_gate_then_advances() -> None:
    pid = uuid4()
    target = ar.resolve_advance_target("1.2")
    with (
        patch.object(
            ar, "gates_pass_with_reason", new=AsyncMock(return_value=(True, ""))
        ),
        patch(
            "app.agents.stage_advancement.advance_stage",
            new=AsyncMock(return_value="advanced_to_define"),
        ) as adv,
    ):
        result = await ar.execute_advance_target(
            project_id=pid, agent_id="supervisor", target=target,
        )
    assert result == "advanced_to_define"
    assert adv.call_args.kwargs["current_stage"] == "discover"


class TestFormatGateMissingZh:
    def test_uses_template_name_zh(self) -> None:
        from dataclasses import dataclass, field

        @dataclass
        class FakeGate:
            missing: dict = field(default_factory=dict)
            counts: dict = field(default_factory=dict)
            requirements: dict = field(default_factory=dict)

        gate = FakeGate(
            missing={"stakeholder": 5},
            counts={"stakeholder": 3},
            requirements={"stakeholder": 8},
        )
        text = ar.format_gate_missing_zh(gate)
        assert "利害關係人" in text  # spec 23 name_zh，不露英文模板鍵
        assert "stakeholder" not in text
        assert "3" in text and "8" in text
