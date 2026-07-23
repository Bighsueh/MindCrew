"""G01 真人硬閘＋#26/#27 移動格帶人鷹架（Phase 42 D1d）。

硬閘（spec 22 §4.3／25 §5.1c／20 §11，推翻 C2「軟」暫定）：硬格（6 格 1.1b/1.2/2.1/
2.2/2.6/2.7）若房內有真人且本回合真人尚未完成有效參與 → 擋推進。time-box 逃生
（skip_gate_check）豁免（spec 20 §11.7 防死鎖）。

涵蓋：
- human_gate_blocks helper（硬格擋/放、軟格不擋、全 AI 不擋、6 格含 2.1、fail-closed）。
- execute_advance_target 整合：kind=sub 硬格也擋（補 gates_pass_with_reason 只覆蓋
  micro/stage 的漏洞）、time-box skip 豁免（不查真人狀態）、真人達成放行。
- watcher._is_ready：真人未達 → 不 ready（防 stall-backstop 每 10s 空轉）。
- #26/#27：2.1/2.6 組長 prompt 注入「先示範→請真人拖＋說→監督非代勞」鷹架。

全 mock，不需 DB / Redis。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.progression import advance_router as ar
from app.progression import watcher as w
from app.progression.advance_router import (
    AdvanceTarget,
    execute_advance_target,
    human_gate_blocks,
)
from app.stages.sub_phases import SUB_PHASES, get_sub_phase, is_hard_gate

# 註：pytest.ini asyncio_mode=auto——async 測試自動執行，無須 module 級 asyncio mark
# （加了會讓本檔同步的 prompt 測試噴 PytestWarning）。

# 6 硬格（spec 22 §4.3）；明確含 2.1（模擬 #27：移動格 move+chat 只做一件不放行）。
_HARD_GRIDS = ["1.1b", "1.2", "2.1", "2.2", "2.6", "2.7"]
_SOFT_GRIDS = ["1.1a", "1.1c", "1.1d", "2.3", "2.4", "2.5"]


def _state(*, has_human: bool, satisfied: bool) -> dict:
    return {"has_human": has_human, "human_satisfied": satisfied}


def _patch_get_state(state: dict):
    """patch round_lock.get_state（human_gate_blocks lazy import 來源）。"""
    return patch("app.agents.round_lock.get_state", new=AsyncMock(return_value=state))


# ── human_gate_blocks helper ────────────────────────────────────────────────


class TestHumanGateHelper:
    async def test_hard_grid_human_not_satisfied_blocks(self) -> None:
        with _patch_get_state(_state(has_human=True, satisfied=False)):
            blocked, reason = await human_gate_blocks(uuid4(), "2.2")
        assert blocked is True
        assert reason  # 內容層大白話、非空
        assert "human_satisfied" not in reason  # 不洩機器鍵名（#29）

    async def test_hard_grid_human_satisfied_passes(self) -> None:
        with _patch_get_state(_state(has_human=True, satisfied=True)):
            blocked, reason = await human_gate_blocks(uuid4(), "2.2")
        assert blocked is False
        assert reason == ""

    async def test_all_ai_room_never_blocks(self) -> None:
        with _patch_get_state(_state(has_human=False, satisfied=False)):
            blocked, _ = await human_gate_blocks(uuid4(), "2.6")
        assert blocked is False

    @pytest.mark.parametrize("soft_sub", _SOFT_GRIDS)
    async def test_soft_grid_never_blocks(self, soft_sub: str) -> None:
        """軟格即使有真人未參與也不擋（硬閘只限硬格）。"""
        with _patch_get_state(_state(has_human=True, satisfied=False)) as gs:
            blocked, _ = await human_gate_blocks(uuid4(), soft_sub)
        assert blocked is False
        gs.assert_not_awaited()  # 軟格在 is_hard_gate 即短路，根本不查 round_lock

    @pytest.mark.parametrize("hard_sub", _HARD_GRIDS)
    async def test_all_six_hard_grids_enforced(self, hard_sub: str) -> None:
        """6 硬格全部 enforce——尤其 2.1（模擬 #27），不可漏。"""
        assert is_hard_gate(get_sub_phase(hard_sub))  # 結構上確為硬格
        with _patch_get_state(_state(has_human=True, satisfied=False)):
            blocked, _ = await human_gate_blocks(uuid4(), hard_sub)
        assert blocked is True

    async def test_two_point_one_is_hard_grid(self) -> None:
        """釘住裁定：2.1 納入硬閘（B 案，依模擬 #27；6/14 列 5 格是漏列）。"""
        assert "2.1" in _HARD_GRIDS
        assert is_hard_gate(get_sub_phase("2.1"))

    async def test_redis_down_fail_closed_blocks(self) -> None:
        """Redis 失敗時 round_lock.get_state 回 has_human=DB真值＋human_satisfied=False
        → 硬閘擋（有真人不誤放行）。"""
        with _patch_get_state(_state(has_human=True, satisfied=False)):
            blocked, _ = await human_gate_blocks(uuid4(), "2.6")
        assert blocked is True

    async def test_unknown_sub_phase_does_not_block(self) -> None:
        assert "9.9z" not in SUB_PHASES
        blocked, _ = await human_gate_blocks(uuid4(), "9.9z")
        assert blocked is False


# ── execute_advance_target 整合 ──────────────────────────────────────────────


class TestExecuteAdvanceHumanGate:
    async def test_kind_sub_hard_grid_enforces_human_gate(self) -> None:
        """補漏洞回歸：kind=sub 的硬格（2.2→2.3）也被擋——gates_pass_with_reason 只覆蓋
        micro/stage，硬閘放在 kind 分派前才不漏。"""
        target = AdvanceTarget(kind="sub", from_sub_phase="2.2", to_sub_phase="2.3")
        with (
            _patch_get_state(_state(has_human=True, satisfied=False)),
            patch(
                "app.agents.stage_advancement.advance_sub_phase",
                new=AsyncMock(return_value="advanced_to_2.3"),
            ) as adv_sub,
        ):
            result = await execute_advance_target(
                uuid4(), "agent_supervisor", target, skip_gate_check=False
            )
        assert result.startswith("sub_advance_blocked:human_gate:")
        adv_sub.assert_not_awaited()  # 擋在推進之前

    async def test_human_satisfied_passes_through(self) -> None:
        """真人本回合已達成 → 硬閘放行、真正推進。"""
        target = AdvanceTarget(kind="sub", from_sub_phase="2.2", to_sub_phase="2.3")
        with (
            _patch_get_state(_state(has_human=True, satisfied=True)),
            patch(
                "app.agents.stage_advancement.advance_sub_phase",
                new=AsyncMock(return_value="advanced_to_2.3"),
            ) as adv_sub,
            patch("app.agents.round_lock.clear", new=AsyncMock()),
        ):
            result = await execute_advance_target(
                uuid4(), "agent_supervisor", target, skip_gate_check=False
            )
        assert result == "advanced_to_2.3"
        adv_sub.assert_awaited_once()

    async def test_time_box_skip_bypasses_human_gate(self) -> None:
        """time-box 逃生（skip_gate_check=True）豁免真人閘——根本不查 round_lock，
        直接推進（2.7→completed）。防死鎖鐵證（spec 20 §11.7）。"""
        target = AdvanceTarget(kind="stage", from_sub_phase="2.7", from_stage="define")
        gs = AsyncMock(return_value=_state(has_human=True, satisfied=False))
        with (
            patch("app.agents.round_lock.get_state", new=gs),
            patch(
                "app.agents.stage_advancement.advance_stage",
                new=AsyncMock(return_value="advanced_to_completed"),
            ) as adv_stage,
            patch("app.agents.round_lock.clear", new=AsyncMock()),
        ):
            result = await execute_advance_target(
                uuid4(), "system_progression", target, skip_gate_check=True
            )
        assert result == "advanced_to_completed"
        adv_stage.assert_awaited_once()
        gs.assert_not_awaited()  # 真人閘被豁免，未查真人狀態


# ── watcher._is_ready 防空轉 ─────────────────────────────────────────────────


class TestIsReadyHumanGate:
    async def test_is_ready_false_when_human_gate_blocks(self) -> None:
        sp = get_sub_phase("2.2")  # 硬格
        with patch.object(
            ar, "human_gate_blocks", new=AsyncMock(return_value=(True, "等使用者"))
        ):
            ready = await w._is_ready(uuid4(), sp)
        assert ready is False

    async def test_is_ready_checks_artifact_gate_when_human_ok(self) -> None:
        sp = get_sub_phase("2.2")
        with (
            patch.object(
                ar, "human_gate_blocks", new=AsyncMock(return_value=(False, ""))
            ),
            patch.object(w, "_gates_pass", new=AsyncMock(return_value=True)) as gp,
        ):
            ready = await w._is_ready(uuid4(), sp)
        assert ready is True
        gp.assert_awaited_once()

    async def test_is_ready_soft_grid_always_true(self) -> None:
        sp = get_sub_phase("2.3")  # 軟格
        ready = await w._is_ready(uuid4(), sp)
        assert ready is True


# ── #26/#27 移動格帶人鷹架（prompt 注入；同步）─────────────────────────────────


class TestMoveGridScaffold:
    def test_scaffold_in_supervisor_2_1(self) -> None:
        from app.agents.prompts.sub_phase_prompts import build_sub_phase_prompt

        p = build_sub_phase_prompt("2.1", "supervisor")
        assert "帶使用者動手" in p
        assert "示範" in p  # #26 crew 先示範
        assert "兩件都做到" in p  # #27 拖＋說雙要求
        assert "不要替他拖" in p  # 監督非代勞

    def test_scaffold_in_supervisor_2_6(self) -> None:
        from app.agents.prompts.sub_phase_prompts import build_sub_phase_prompt

        p = build_sub_phase_prompt("2.6", "supervisor")
        assert "帶使用者動手" in p
        assert "示範搬一張" in p

    def test_scaffold_not_in_crew_role(self) -> None:
        """帶人鷹架是組長職責，crew prompt 不注入該段。"""
        from app.agents.prompts.sub_phase_prompts import build_sub_phase_prompt

        p = build_sub_phase_prompt("2.1", "crew")
        assert "帶使用者動手（這一關要請他親自做）" not in p

    def test_no_scaffold_on_non_move_grid(self) -> None:
        from app.agents.prompts.sub_phase_prompts import build_sub_phase_prompt

        p = build_sub_phase_prompt("2.2", "supervisor")
        assert "帶使用者動手（這一關要請他親自做）" not in p


class TestSupervisorReasonNoMachineLeak:
    """組長唸出推進被擋原因時，不得露「human_gate:」機器前綴（#29）。"""

    def test_human_gate_reason_strips_machine_prefix(self) -> None:
        from app.agents.act_progression import _blocked_reason_zh

        msg = _blocked_reason_zh(
            "sub_advance_blocked:human_gate:這一步想請使用者也動手參與一下，"
            "等他這一回合做了我們再往下。"
        )
        assert "human_gate" not in msg
        assert "這一步想請使用者" in msg
