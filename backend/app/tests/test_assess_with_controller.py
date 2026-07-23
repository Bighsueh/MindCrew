"""Phase 28 — AssessEngine × TurnController integration.

確認 Rule 0 / Rule 0.2 / Rule 1 在三個 policy 下行為符合預期。
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents import reveal_queue
from app.agents.assess import AssessEngine
from app.agents.turn_controller import (
    CuedPolicy,
    OpenFloorPolicy,
    RoundRobinPolicy,
)


def _ctx(
    *,
    my_seat: str = "crew_1",
    invited: str | None = None,
    sub_phase: str | None = None,
    comm_mode: str = "discussion",
    comm_strategy: str = "",
    recent_chat: list[dict] | None = None,
    reveal_queue_list: list[str] | None = None,
) -> dict:
    blackboard: dict = {}
    if invited:
        blackboard["coordination_directive"] = {"invited_speaker": invited}
    return {
        "my_seat": my_seat,
        "seats": [
            {"role": "supervisor", "type": "ai"},
            {"role": "crew_1", "type": "ai"},
            {"role": "crew_2", "type": "ai"},
            {"role": "crew_3", "type": "ai"},
            {"role": "crew_4", "type": "ai"},
        ],
        "blackboard": blackboard,
        "current_sub_phase": sub_phase,
        "comm_mode": comm_mode,
        "phase_strategy": {
            "comm_strategy": comm_strategy,
            "comm_goal": "",
            "supervisor_mode": "participant",
        },
        "recent_chat": recent_chat or [],
        "reveal_queue": reveal_queue_list or [],
    }


# ---------------------------------------------------------------------------
# Rule 0 — Cued strategy gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assess_cued_uninvited_crew_waits():
    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(my_seat="crew_1", invited="crew_3"),
        agent_id="agent_crew_1",
        controller=controller,
    )
    assert result.decision == "wait"
    assert result.rule == "rule_0_turn_gate"


@pytest.mark.asyncio
async def test_assess_cued_invited_crew_passes_gate():
    """invited 是我 → controller.can_act=True → Rule 0 不擋"""
    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(my_seat="crew_2", invited="crew_2"),
        agent_id="agent_crew_2",
        controller=controller,
    )
    # 應該 fall through 到後續 rule (rule_5_idle / rule_7_thread_aware / rule_8_default)
    assert result.rule != "rule_0_turn_gate"


@pytest.mark.asyncio
async def test_assess_cued_all_crew_lets_crew_pass_gate():
    """D4：invited_speaker='all_crew' → 任一 crew 通過 gate（開放全體）。"""
    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(my_seat="crew_3", invited="all_crew"),
        agent_id="agent_crew_3",
        controller=controller,
    )
    assert result.rule != "rule_0_turn_gate"


@pytest.mark.asyncio
async def test_assess_cued_warmup_deadlock_breaker_passes_gate():
    """Phase 38 (spec/28 §7)：暖場 0.0a 移除 open-floor surge，改 cued MC 逐一邀。

    死結破除仍在：MC(supervisor) 講過但 crew 全沒講 → crew 可通過 turn gate（不卡死）。
    """
    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(
            my_seat="crew_2",
            sub_phase="0.0a",
            recent_chat=[{"sender_id": "agent_supervisor", "sender": "AI 引導者"}],
        ),
        agent_id="agent_crew_2",
        controller=controller,
    )
    assert result.rule != "rule_0_turn_gate"


@pytest.mark.asyncio
async def test_assess_cued_uninvited_crew_waits_even_after_supervisor():
    """D3：上一句是 supervisor 也不再讓未被點名的 crew 越權發言。"""
    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(
            my_seat="crew_1",
            invited="crew_3",
            recent_chat=[_msg("supervisor", "我們繼續討論吧")],
        ),
        agent_id="agent_crew_1",
        controller=controller,
    )
    assert result.decision == "wait"
    assert result.rule == "rule_0_turn_gate"


@pytest.mark.asyncio
async def test_assess_round_robin_non_head_waits_via_turn_gate():
    """D2：RR 非隊首一律經 turn gate → wait（修正前完全不過閘）。"""
    engine = AssessEngine()
    pid = uuid4()
    await reveal_queue.start_reveal_round(pid, ["crew_2", "crew_1"], "2.1")
    try:
        controller = RoundRobinPolicy(pid)
        result = await engine.evaluate(
            context=_ctx(my_seat="crew_1", sub_phase="2.1"),
            agent_id="agent_crew_1",
            controller=controller,
        )
        assert result.decision == "wait"
        assert result.rule == "rule_0_turn_gate"
        assert result.details["policy"] == "round_robin"
    finally:
        await reveal_queue.reset(pid)


@pytest.mark.asyncio
async def test_assess_round_robin_head_passes_turn_gate():
    """RR 隊首通過 turn gate。"""
    engine = AssessEngine()
    pid = uuid4()
    await reveal_queue.start_reveal_round(pid, ["crew_1", "crew_2"], "2.1")
    try:
        controller = RoundRobinPolicy(pid)
        result = await engine.evaluate(
            context=_ctx(my_seat="crew_1", sub_phase="2.1"),
            agent_id="agent_crew_1",
            controller=controller,
        )
        assert result.rule != "rule_0_turn_gate"
    finally:
        await reveal_queue.reset(pid)


@pytest.mark.asyncio
async def test_assess_open_floor_passes_turn_gate_by_default():
    """OF 無人 raise_hand → 預設通過 gate（自由發言不受影響）。"""
    engine = AssessEngine()
    controller = OpenFloorPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(my_seat="crew_1"),
        agent_id="agent_crew_1",
        controller=controller,
    )
    assert result.rule != "rule_0_turn_gate"


@pytest.mark.asyncio
async def test_assess_open_floor_non_priority_waits_during_raise_hand():
    """D5：他人 raise_hand 期間，非優先席位的 AI 經 turn gate → wait。"""
    from app.agents.turn_controller import (
        consume_user_priority_speak,
        mark_user_priority_speak,
    )

    engine = AssessEngine()
    pid = uuid4()
    await mark_user_priority_speak(pid, "crew_1")  # 人類 crew_1 舉手
    try:
        controller = OpenFloorPolicy(pid)
        result = await engine.evaluate(
            context=_ctx(my_seat="crew_2"),  # 非優先席位
            agent_id="agent_crew_2",
            controller=controller,
        )
        assert result.decision == "wait"
        assert result.rule == "rule_0_turn_gate"
        assert result.details["policy"] == "open_floor"
    finally:
        await consume_user_priority_speak(pid)


@pytest.mark.asyncio
async def test_assess_cued_same_tick_mention_overrides_gate():
    """cued：同 tick 被 @mention（尚未寫入 invited）→ 放行（點名機制）。"""
    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(
            my_seat="crew_1",
            recent_chat=[_msg("supervisor", "@crew_1 你的看法呢？")],
        ),
        agent_id="agent_crew_1",
        controller=controller,
    )
    assert result.rule != "rule_0_turn_gate"


# ---------------------------------------------------------------------------
# Rule 1 — mention only intervenes in Cued
# ---------------------------------------------------------------------------


def _msg(sender: str, content: str) -> dict:
    return {
        "sender": sender,
        "sender_id": sender,
        "sender_type": "ai",
        "content": content,
    }


@pytest.mark.asyncio
async def test_assess_mention_intervenes_in_cued():
    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(
            my_seat="crew_1",
            invited="crew_1",  # ensure Rule 0 doesn't block
            recent_chat=[_msg("supervisor", "@crew_1 你的看法呢？")],
        ),
        agent_id="agent_crew_1",
        controller=controller,
    )
    assert result.decision == "intervene"
    assert result.rule == "rule_1_mention"


@pytest.mark.asyncio
async def test_assess_mention_does_not_intervene_in_round_robin():
    """RR 下 mention 不再構成 intervene 訊號 (避免繞過輪流)。"""
    engine = AssessEngine()
    pid = uuid4()
    await reveal_queue.start_reveal_round(pid, ["crew_2", "crew_1"], "2.1")
    try:
        controller = RoundRobinPolicy(pid)
        result = await engine.evaluate(
            context=_ctx(
                my_seat="crew_1",
                sub_phase="2.1",
                recent_chat=[_msg("supervisor", "@crew_1 講一下")],
            ),
            agent_id="agent_crew_1",
            controller=controller,
        )
        assert result.rule != "rule_1_mention"
    finally:
        await reveal_queue.reset(pid)


@pytest.mark.asyncio
async def test_assess_mention_does_not_intervene_in_open_floor():
    engine = AssessEngine()
    controller = OpenFloorPolicy(uuid4())
    result = await engine.evaluate(
        context=_ctx(
            my_seat="crew_1",
            recent_chat=[_msg("supervisor", "@crew_1 講一下")],
        ),
        agent_id="agent_crew_1",
        controller=controller,
    )
    assert result.rule != "rule_1_mention"


# ---------------------------------------------------------------------------
# Rule 0.2 — reveal_round under controller path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assess_reveal_round_uses_controller_in_round_robin():
    """comm_mode=reveal_round 時，RR controller 應該守 queue head。"""
    engine = AssessEngine()
    pid = uuid4()
    await reveal_queue.start_reveal_round(pid, ["supervisor", "crew_1"], "1.1c")
    try:
        controller = RoundRobinPolicy(pid)
        result = await engine.evaluate(
            context=_ctx(
                my_seat="crew_1",
                comm_mode="reveal_round",
                sub_phase="1.1c",
                reveal_queue_list=["supervisor", "crew_1"],
            ),
            agent_id="agent_crew_1",
            controller=controller,
        )
        assert result.decision == "wait"
        assert result.rule == "rule_0_2_reveal_not_my_turn"
        assert result.details["next_seat"] == "supervisor"
    finally:
        await reveal_queue.reset(pid)


@pytest.mark.asyncio
async def test_assess_reveal_round_falls_back_when_controller_not_rr():
    """非 RR controller 下，仍走既有 context['reveal_queue'] 兜底路徑。"""
    engine = AssessEngine()
    controller = CuedPolicy(uuid4())  # 非 RR
    result = await engine.evaluate(
        context=_ctx(
            my_seat="crew_1",
            comm_mode="reveal_round",
            reveal_queue_list=["supervisor", "crew_1"],
            invited="crew_1",  # pass Rule 0 (cued gate)
        ),
        agent_id="agent_crew_1",
        controller=controller,
    )
    assert result.decision == "wait"
    assert result.rule == "rule_0_2_reveal_not_my_turn"


# ---------------------------------------------------------------------------
# 病根 D 軟護欄 — _resolve_target_count + rule_x_volume_overflow
# ---------------------------------------------------------------------------


def test_resolve_target_count_known_sub_phases():
    from app.agents.assess import _resolve_target_count

    assert _resolve_target_count("1.1a") == 5
    # Phase 42 C1：舊 1.5 移除；新 1.2（發想痛點）量爆軟上限 12。
    assert _resolve_target_count("1.2") == 12


def test_resolve_target_count_unknown_or_empty():
    from app.agents.assess import _resolve_target_count

    assert _resolve_target_count("") is None
    assert _resolve_target_count("nonexistent") is None
    # target_count=None 的 sub-phase（如 2.3）→ None
    assert _resolve_target_count("2.3") is None


@pytest.mark.asyncio
async def test_rule_x_volume_overflow_triggers_when_over_soft_cap():
    """便條數超過 sub-phase target_count×係數 → intervene rule_x_volume_overflow。

    截圖情境：暖場區（1.1a，target=5）累積到遠超量（~150 張）卻不整理。
    """
    engine = AssessEngine()
    ctx = _ctx(my_seat="crew_1", sub_phase="1.1a")
    # target_count=5；5*3=15，給 60 張遠超軟上限
    ctx["canvas_state"] = {"summary": {"total_notes": 60, "orderliness_score": 0.9}}
    result = await engine.evaluate(
        context=ctx,
        agent_id="agent_crew_1",
    )
    assert result.decision == "intervene"
    assert result.rule == "rule_x_volume_overflow"
    assert result.details["target_count"] == 5


# ---------------------------------------------------------------------------
# Rule 0.8 — 暖場人類優先（0.0a，Phase 38 retarget 自 1.1a）
# ---------------------------------------------------------------------------


def _warmup_ctx(my_seat: str, *, human_spoke: bool, with_human: bool = True) -> dict:
    ctx = _ctx(my_seat=my_seat, sub_phase="0.0a")
    if with_human:
        ctx["seats"] = ctx["seats"] + [{"role": "human_1", "type": "human"}]
    ctx["recent_chat"] = (
        [{"sender_type": "human", "content": "我來分享一下"}]
        if human_spoke else [{"sender_type": "ai", "content": "嗨"}]
    )
    return ctx


# v2.0（Phase 42 A2，spec 20 §11.5）：Rule 0.8 由「暖場人類第一次發言前」泛化為
# 「每回合重新上鎖」，執行點改呼叫 round_lock.is_crew_blocked。回合鎖狀態機本身的
# 凍結 / 解鎖 / 全 AI 不凍 等行為在 test_round_lock.py 對真實狀態機驗證；此處只驗
# ASSESS 接線：有呼叫、組長豁免、無 _project_id 不介入。


@pytest.mark.asyncio
async def test_rule_0_8_round_lock_blocks_crew(monkeypatch):
    from app.agents import round_lock

    async def _blocked(pid, sub, seat):
        return True, "先把空間留給使用者"

    monkeypatch.setattr(round_lock, "is_crew_blocked", _blocked)
    ctx = _warmup_ctx("crew_1", human_spoke=False)
    ctx["_project_id"] = uuid4()
    ctx["current_sub_phase"] = "0.0a"
    result = await AssessEngine().evaluate(context=ctx, agent_id="agent_crew_1")
    assert result.decision == "wait"
    assert result.rule == "rule_0_8_round_lock"


@pytest.mark.asyncio
async def test_rule_0_8_supervisor_exempt(monkeypatch):
    from app.agents import round_lock

    async def _blocked(pid, sub, seat):
        return True, "x"

    monkeypatch.setattr(round_lock, "is_crew_blocked", _blocked)
    ctx = _warmup_ctx("supervisor", human_spoke=False)
    ctx["_project_id"] = uuid4()
    ctx["current_sub_phase"] = "0.0a"
    result = await AssessEngine().evaluate(context=ctx, agent_id="agent_supervisor")
    assert result.rule != "rule_0_8_round_lock"


@pytest.mark.asyncio
async def test_rule_0_8_unblocked_crew_proceeds(monkeypatch):
    from app.agents import round_lock

    async def _free(pid, sub, seat):
        return False, ""

    monkeypatch.setattr(round_lock, "is_crew_blocked", _free)
    ctx = _warmup_ctx("crew_1", human_spoke=True)
    ctx["_project_id"] = uuid4()
    ctx["current_sub_phase"] = "0.0a"
    result = await AssessEngine().evaluate(context=ctx, agent_id="agent_crew_1")
    assert result.rule != "rule_0_8_round_lock"


@pytest.mark.asyncio
async def test_rule_0_8_skipped_without_project_id(monkeypatch):
    # 無 _project_id（純單元 context）→ 回合鎖不介入、不應呼叫 is_crew_blocked。
    from app.agents import round_lock

    async def _boom(pid, sub, seat):
        raise AssertionError("不應在缺 _project_id 時呼叫")

    monkeypatch.setattr(round_lock, "is_crew_blocked", _boom)
    result = await AssessEngine().evaluate(
        context=_warmup_ctx("crew_1", human_spoke=False),
        agent_id="agent_crew_1",
    )
    assert result.rule != "rule_0_8_round_lock"


# ---------------------------------------------------------------------------
# Rule 2.5 — 多訊息連發 debounce（B2）
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_human_messaged_recently_helper() -> None:
    import time as _t

    engine = AssessEngine()
    assert engine._human_messaged_recently(
        {"_human_last_message_timestamp": _t.time()}
    ) is True
    assert engine._human_messaged_recently(
        {"_human_last_message_timestamp": _t.time() - 5.0}
    ) is False
    assert engine._human_messaged_recently({}) is False


@pytest.mark.asyncio
async def test_rule_2_5_supervisor_waits_after_recent_human_message() -> None:
    """人類剛發訊息（連發中）→ 組長 Rule 2.5 wait，等連發停了再回最後一則。"""
    import time as _t

    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    # 非 fresh project（recent_chat 有訊息）→ 避免 rule_0_1_fresh_project 先 intervene。
    ctx = _ctx(
        my_seat="supervisor",
        recent_chat=[
            {
                "sender_type": "human",
                "sender_id": "human_creator",
                "content": "可以當電腦機殼的濾網",
            }
        ],
    )
    ctx["_human_last_message_timestamp"] = _t.time()
    result = await engine.evaluate(
        context=ctx, agent_id="agent_supervisor", controller=controller
    )
    assert result.decision == "wait"
    assert result.rule == "rule_2_5_human_message_recent"


@pytest.mark.asyncio
async def test_rule_2_5_does_not_gate_when_message_is_old() -> None:
    """人類訊息已過 debounce 窗（>2s）→ Rule 2.5 不擋（fall through）。"""
    import time as _t

    engine = AssessEngine()
    controller = CuedPolicy(uuid4())
    ctx = _ctx(my_seat="supervisor")
    ctx["_human_last_message_timestamp"] = _t.time() - 10.0
    result = await engine.evaluate(
        context=ctx, agent_id="agent_supervisor", controller=controller
    )
    assert result.rule != "rule_2_5_human_message_recent"
