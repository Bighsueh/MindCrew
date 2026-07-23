"""Phase 28 — TurnController unit tests.

每個 policy 的 `is_my_turn` / `on_speak` / `on_pass` / `compute_cooldown`
各分支獨立測。RoundRobinPolicy 的「1.1c 不自動重啟、其他自動重啟」是
論文驗收關鍵 case，特別覆蓋。
"""
from __future__ import annotations

import math
from uuid import uuid4

import pytest

from app.agents import reveal_queue
from app.agents.turn_controller import (
    CuedPolicy,
    OpenFloorPolicy,
    RoundRobinPolicy,
    TurnPolicy,
    consume_user_priority_speak,
    get_controller,
    mark_user_priority_speak,
    parse_policy,
    peek_user_priority_speak,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(
    *,
    my_seat: str = "crew_1",
    invited: str | None = None,
    seats: list[dict] | None = None,
    sub_phase: str | None = None,
    recent_chat: list[dict] | None = None,
) -> dict:
    """Construct a minimal assess context dict for tests."""
    blackboard: dict = {}
    if invited:
        blackboard["coordination_directive"] = {"invited_speaker": invited}
    return {
        "my_seat": my_seat,
        "seats": seats or [
            {"role": "supervisor", "type": "ai"},
            {"role": "crew_1", "type": "ai"},
            {"role": "crew_2", "type": "ai"},
            {"role": "crew_3", "type": "ai"},
            {"role": "crew_4", "type": "ai"},
        ],
        "blackboard": blackboard,
        "current_sub_phase": sub_phase,
        "recent_chat": recent_chat or [],
    }


# ---------------------------------------------------------------------------
# Factory + parse helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_controller_returns_matching_policy():
    pid = uuid4()
    assert isinstance(await get_controller("cued", pid), CuedPolicy)
    assert isinstance(await get_controller("round_robin", pid), RoundRobinPolicy)
    assert isinstance(await get_controller("open_floor", pid), OpenFloorPolicy)
    # 不合法字串 → 預設 cued (避免 PATCH 異常造成 agent loop 崩)
    assert isinstance(await get_controller("nonsense", pid), CuedPolicy)


def test_parse_policy_handles_enum_and_str_and_invalid():
    assert parse_policy(TurnPolicy.OPEN_FLOOR) == TurnPolicy.OPEN_FLOOR
    assert parse_policy("round_robin") == TurnPolicy.ROUND_ROBIN
    assert parse_policy(None) == TurnPolicy.CUED
    assert parse_policy("") == TurnPolicy.CUED


# ---------------------------------------------------------------------------
# CuedPolicy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cued_supervisor_always_can_act():
    policy = CuedPolicy(uuid4())
    decision = await policy.is_my_turn("supervisor", _ctx(my_seat="supervisor"))
    assert decision.can_act
    assert "speak" in decision.allowed_actions


@pytest.mark.asyncio
async def test_cued_invited_crew_can_act():
    policy = CuedPolicy(uuid4())
    decision = await policy.is_my_turn(
        "crew_2", _ctx(my_seat="crew_2", invited="crew_2")
    )
    assert decision.can_act
    assert decision.reason == "cued_invited"


@pytest.mark.asyncio
async def test_cued_uninvited_crew_must_wait():
    policy = CuedPolicy(uuid4())
    decision = await policy.is_my_turn(
        "crew_1", _ctx(my_seat="crew_1", invited="crew_3")
    )
    assert not decision.can_act
    assert decision.next_speaker == "crew_3"


@pytest.mark.asyncio
async def test_cued_all_crew_lets_any_crew_act():
    """D4：invited_speaker='all_crew' → 任一 crew can_act，cooldown=0。"""
    policy = CuedPolicy(uuid4())
    for seat in ("crew_1", "crew_2", "crew_3"):
        decision = await policy.is_my_turn(seat, _ctx(my_seat=seat, invited="all_crew"))
        assert decision.can_act, seat
        assert decision.reason == "cued_invited"
        cd = await policy.compute_cooldown(
            seat, _ctx(my_seat=seat, invited="all_crew"), is_supervisor=False
        )
        assert cd == 0.0


@pytest.mark.asyncio
async def test_cued_directive_present_but_none_does_not_crash():
    """D8：coordination_directive 為 None（非缺鍵）時不得 NoneType 崩潰。"""
    policy = CuedPolicy(uuid4())
    ctx = {
        "my_seat": "crew_1",
        "seats": [{"role": "crew_1", "type": "ai"}],
        "blackboard": {"coordination_directive": None},
        "recent_chat": [],
    }
    decision = await policy.is_my_turn("crew_1", ctx)
    assert not decision.can_act
    assert decision.reason == "cued_not_invited"
    cd = await policy.compute_cooldown("crew_1", ctx, is_supervisor=False)
    assert math.isinf(cd)


@pytest.mark.asyncio
async def test_cued_warmup_no_surge_waits_for_mc_invite():
    """Phase 38 (spec/28 §7)：暖場 0.0a 移除 open-floor surge。

    無明確點名、且 supervisor(MC) 尚未發話 → crew 不自動開放，等組長逐一邀
    （避免多 AI 同拍湧上灌爆暖場）。死結破除改由 supervisor 講過後的 B 分支保底。
    """
    policy = CuedPolicy(uuid4())
    ctx = _ctx(my_seat="crew_2", sub_phase="0.0a")  # no invited_speaker, no chat
    d = await policy.is_my_turn("crew_2", ctx)
    assert not d.can_act
    assert d.reason == "cued_not_invited"


@pytest.mark.asyncio
async def test_cued_warmup_deadlock_breaker_still_applies():
    """Phase 38：暖場 0.0a 仍保留死結破除——MC 講過但 crew 全沒講 → 開放。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(
        my_seat="crew_2",
        sub_phase="0.0a",
        recent_chat=[{"sender_id": "agent_supervisor", "sender": "AI 引導者"}],
    )
    d = await policy.is_my_turn("crew_2", ctx)
    assert d.can_act
    assert d.reason == "cued_open_floor"


@pytest.mark.asyncio
async def test_cued_deadlock_breaker_supervisor_spoke_crew_silent():
    """B：非破冰、無點名、supervisor 講過但 crew 沒講 → 開放（避免卡死）。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(
        my_seat="crew_2",
        sub_phase="1.2",
        recent_chat=[{"sender_id": "agent_supervisor", "sender": "AI 引導者"}],
    )
    d = await policy.is_my_turn("crew_2", ctx)
    assert d.can_act
    assert d.reason == "cued_open_floor"


@pytest.mark.asyncio
async def test_cued_strict_again_once_crew_participating():
    """非破冰、無點名、crew 已發過言 → 回到嚴格等待點名（不無限開放）。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(
        my_seat="crew_2",
        sub_phase="1.2",
        recent_chat=[
            {"sender_id": "agent_supervisor"},
            {"sender_id": "agent_crew_3"},
        ],
    )
    d = await policy.is_my_turn("crew_2", ctx)
    assert not d.can_act
    assert d.reason == "cued_not_invited"


@pytest.mark.asyncio
async def test_cued_specific_invite_still_gates_others_in_icebreaker():
    """破冰中 supervisor 明確點名 crew_3 → crew_2 仍須等待（supervisor 控制優先）。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(my_seat="crew_2", sub_phase="1.1a", invited="crew_3")
    d = await policy.is_my_turn("crew_2", ctx)
    assert not d.can_act
    assert d.reason == "cued_not_invited"


@pytest.mark.asyncio
async def test_cued_cooldown_supervisor_uses_base():
    policy = CuedPolicy(uuid4())
    cooldown = await policy.compute_cooldown(
        "supervisor", _ctx(my_seat="supervisor"), is_supervisor=True
    )
    # all-AI 預設 40s (見 _supervisor_cued_cooldown)
    assert cooldown == pytest.approx(40.0, abs=5.0)


@pytest.mark.asyncio
async def test_cued_cooldown_invited_crew_is_zero():
    policy = CuedPolicy(uuid4())
    cooldown = await policy.compute_cooldown(
        "crew_2",
        _ctx(my_seat="crew_2", invited="crew_2"),
        is_supervisor=False,
    )
    assert cooldown == 0.0


@pytest.mark.asyncio
async def test_cued_cooldown_uninvited_crew_is_inf():
    policy = CuedPolicy(uuid4())
    cooldown = await policy.compute_cooldown(
        "crew_1",
        _ctx(my_seat="crew_1", invited="crew_3"),
        is_supervisor=False,
    )
    assert math.isinf(cooldown)


def test_cued_system_prompt_mentions_cuing():
    text = CuedPolicy(uuid4()).system_prompt_fragment()
    assert "點名" in text


# ---------------------------------------------------------------------------
# CuedPolicy — Phase 42 (1.1a 隊友沉默修復): round_lock 單席位死結破除（真人房）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cued_human_room_deadlock_opens_single_seat():
    """真人房死結：context 注入 _cued_open_seat → 只該席位 can_act/cooldown=0，其餘 inf。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(my_seat="crew_1", sub_phase="1.1a")
    ctx["_round_lock_has_human"] = True
    ctx["_cued_open_seat"] = "crew_1"

    d1 = await policy.is_my_turn("crew_1", ctx)
    assert d1.can_act and d1.reason == "cued_open_floor"
    assert await policy.compute_cooldown("crew_1", ctx, is_supervisor=False) == 0.0

    ctx2 = _ctx(my_seat="crew_2", sub_phase="1.1a")
    ctx2["_round_lock_has_human"] = True
    ctx2["_cued_open_seat"] = "crew_1"  # 只放 crew_1，crew_2 仍須等
    d2 = await policy.is_my_turn("crew_2", ctx2)
    assert not d2.can_act and d2.reason == "cued_not_invited"
    assert math.isinf(await policy.compute_cooldown("crew_2", ctx2, is_supervisor=False))


@pytest.mark.asyncio
async def test_cued_human_room_leftover_chat_does_not_poison():
    """根因修復：真人房改讀 round_lock；recent_chat 有殘留 crew 訊息也不再誤關閘。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(
        my_seat="crew_1",
        sub_phase="1.1a",
        # 上一關 0.0a 殘留的 crew 訊息（舊邏輯會誤判「crew 已講過」而永不開閘）。
        recent_chat=[{"sender_id": "agent_crew_3", "sender": "隊友"}],
    )
    ctx["_round_lock_has_human"] = True
    ctx["_cued_open_seat"] = "crew_1"
    d = await policy.is_my_turn("crew_1", ctx)
    assert d.can_act and d.reason == "cued_open_floor"


@pytest.mark.asyncio
async def test_cued_human_room_no_open_seat_when_crew_participated():
    """真人房已有 crew 出過聲（上游算出 _cued_open_seat=None）→ branch B 不再開放。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(
        my_seat="crew_1",
        sub_phase="1.1a",
        recent_chat=[{"sender_id": "agent_supervisor", "sender": "AI 引導者"}],
    )
    ctx["_round_lock_has_human"] = True
    ctx["_cued_open_seat"] = None
    d = await policy.is_my_turn("crew_1", ctx)
    assert not d.can_act and d.reason == "cued_not_invited"


@pytest.mark.asyncio
async def test_cued_explicit_invite_overrides_open_seat():
    """Layer1（組長明確點名）優先於 Layer2（安全網）：有 invited_speaker 時不諮詢 branch B。"""
    policy = CuedPolicy(uuid4())
    # 組長已 set_directive 邀 crew_2；安全網本想放 crew_1 → crew_1 仍須等（無雙放/灌爆）。
    ctx1 = _ctx(my_seat="crew_1", sub_phase="1.1a", invited="crew_2")
    ctx1["_round_lock_has_human"] = True
    ctx1["_cued_open_seat"] = "crew_1"
    d1 = await policy.is_my_turn("crew_1", ctx1)
    assert not d1.can_act and d1.reason == "cued_not_invited"

    ctx2 = _ctx(my_seat="crew_2", sub_phase="1.1a", invited="crew_2")
    ctx2["_round_lock_has_human"] = True
    ctx2["_cued_open_seat"] = "crew_1"
    d2 = await policy.is_my_turn("crew_2", ctx2)
    assert d2.can_act and d2.reason == "cued_invited"


# ---------------------------------------------------------------------------
# RoundRobinPolicy
# ---------------------------------------------------------------------------


@pytest.fixture
async def fresh_rr_project():
    """每個 test 用新 project_id，並確保 reveal_queue 空。"""
    pid = uuid4()
    await reveal_queue.reset(pid)
    yield pid
    await reveal_queue.reset(pid)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_round_robin_auto_starts_when_queue_empty(fresh_rr_project):
    pid = fresh_rr_project
    policy = RoundRobinPolicy(pid)
    # 第一次 is_my_turn 應該自動開一輪 (sub_phase != "1.1c")
    decision = await policy.is_my_turn(
        "supervisor", _ctx(my_seat="supervisor", sub_phase="2.1")
    )
    assert decision.can_act
    assert decision.next_speaker == "supervisor"
    queue = await reveal_queue.get_queue(pid)
    assert queue[0] == "supervisor"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_round_robin_advances_after_speak(fresh_rr_project):
    pid = fresh_rr_project
    policy = RoundRobinPolicy(pid)
    await reveal_queue.start_reveal_round(
        pid, ["supervisor", "crew_1", "crew_2"], "2.1"
    )
    ctx = _ctx(my_seat="supervisor", sub_phase="2.1")

    d1 = await policy.is_my_turn("supervisor", ctx)
    assert d1.can_act

    await policy.on_speak("supervisor", ctx)

    d2 = await policy.is_my_turn("supervisor", ctx)
    assert not d2.can_act
    assert d2.next_speaker == "crew_1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_round_robin_auto_restarts_outside_1_1c(fresh_rr_project):
    """非 1.1c sub-phase 下，輪完一圈自動重啟一輪。"""
    pid = fresh_rr_project
    policy = RoundRobinPolicy(pid)
    seat_order = ["supervisor", "crew_1"]
    await reveal_queue.start_reveal_round(pid, seat_order, "2.1")

    # 全部講完 → queue 空
    await policy.on_speak("supervisor", _ctx(my_seat="supervisor", sub_phase="2.1"))
    await policy.on_speak("crew_1", _ctx(my_seat="crew_1", sub_phase="2.1"))
    assert await reveal_queue.is_round_complete(pid)

    # 下一個 is_my_turn 自動以預設順序重啟 — supervisor 應該又能講
    d = await policy.is_my_turn(
        "supervisor", _ctx(my_seat="supervisor", sub_phase="2.1")
    )
    assert d.can_act, "RoundRobin 應該在非 1.1c 時自動重啟"
    queue_after = await reveal_queue.get_queue(pid)
    assert queue_after, "queue 應該被自動填回"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_round_robin_does_not_auto_restart_in_1_1c(fresh_rr_project):
    """1.1c 是 phase machine 自管的場域，controller 不可自動重啟。"""
    pid = fresh_rr_project
    policy = RoundRobinPolicy(pid)
    await reveal_queue.start_reveal_round(pid, ["supervisor"], "1.1c")
    await policy.on_speak("supervisor", _ctx(my_seat="supervisor", sub_phase="1.1c"))
    assert await reveal_queue.is_round_complete(pid)

    d = await policy.is_my_turn(
        "supervisor", _ctx(my_seat="supervisor", sub_phase="1.1c")
    )
    assert not d.can_act
    assert d.reason == "round_robin_phase_machine_owned_empty"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_round_robin_cooldown_is_zero_or_inf(fresh_rr_project):
    pid = fresh_rr_project
    policy = RoundRobinPolicy(pid)
    await reveal_queue.start_reveal_round(pid, ["supervisor", "crew_1"], "2.1")

    cd_my_turn = await policy.compute_cooldown(
        "supervisor",
        _ctx(my_seat="supervisor", sub_phase="2.1"),
        is_supervisor=True,
    )
    assert cd_my_turn == 0.0

    cd_not_my_turn = await policy.compute_cooldown(
        "crew_1",
        _ctx(my_seat="crew_1", sub_phase="2.1"),
        is_supervisor=False,
    )
    assert math.isinf(cd_not_my_turn)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reveal_queue_timeout_advances_human_head(fresh_rr_project):
    """D1：reveal_queue.timeout_advance_human_head 推進逾時的人類隊首。"""
    pid = fresh_rr_project
    await reveal_queue.start_reveal_round(pid, ["crew_1", "crew_2"], "2.1")
    # crew_1 是人類隊首；timeout_s=0 → 立即視為逾時 pass
    advanced = await reveal_queue.timeout_advance_human_head(pid, {"crew_1"}, 0.0)
    assert advanced
    assert await reveal_queue.peek_next_seat(pid) == "crew_2"
    # 非人類隊首 → no-op
    advanced2 = await reveal_queue.timeout_advance_human_head(pid, {"crew_1"}, 0.0)
    assert not advanced2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_round_robin_is_my_turn_skips_timed_out_human(fresh_rr_project):
    """D1：RR 隊首為人類且逾時 → is_my_turn 自動推進，下一席位可動。"""
    pid = fresh_rr_project
    policy = RoundRobinPolicy(pid)
    # 立即逾時：用 monkeypatch 把常數壓成 0，避免測試等 45s
    import app.agents.turn_controller as tc

    seats = [
        {"role": "crew_1", "type": "human"},
        {"role": "crew_2", "type": "ai"},
    ]
    await reveal_queue.start_reveal_round(pid, ["crew_1", "crew_2"], "2.1")
    orig = tc.RR_HUMAN_TURN_TIMEOUT_SECONDS
    tc.RR_HUMAN_TURN_TIMEOUT_SECONDS = 0.0
    try:
        d = await policy.is_my_turn(
            "crew_2", _ctx(my_seat="crew_2", seats=seats, sub_phase="2.1")
        )
        assert d.can_act, "人類隊首逾時後，crew_2 應該輪到"
        assert d.reason == "round_robin_my_turn"
    finally:
        tc.RR_HUMAN_TURN_TIMEOUT_SECONDS = orig


def test_round_robin_system_prompt_mentions_order():
    text = RoundRobinPolicy(uuid4()).system_prompt_fragment()
    assert "輪流" in text


# ---------------------------------------------------------------------------
# OpenFloorPolicy
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_floor_is_my_turn_default_true():
    pid = uuid4()
    await consume_user_priority_speak(pid)  # ensure clean
    policy = OpenFloorPolicy(pid)
    d = await policy.is_my_turn("crew_1", _ctx(my_seat="crew_1"))
    assert d.can_act
    assert "raise_hand" in d.allowed_actions


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_floor_yields_to_priority_speaker():
    pid = uuid4()
    await mark_user_priority_speak(pid, "crew_3")
    try:
        policy = OpenFloorPolicy(pid)
        # crew_1 (非優先者) → wait
        d_other = await policy.is_my_turn("crew_1", _ctx(my_seat="crew_1"))
        assert not d_other.can_act
        assert d_other.next_speaker == "crew_3"
        # crew_3 (優先者本人) → can_act
        d_priority = await policy.is_my_turn("crew_3", _ctx(my_seat="crew_3"))
        assert d_priority.can_act
    finally:
        await consume_user_priority_speak(pid)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_floor_priority_consumed_after_speak():
    pid = uuid4()
    await mark_user_priority_speak(pid, "crew_3")
    try:
        policy = OpenFloorPolicy(pid)
        assert await peek_user_priority_speak(pid) == "crew_3"
        await policy.on_speak("crew_3", _ctx(my_seat="crew_3"))
        assert await peek_user_priority_speak(pid) is None
    finally:
        await consume_user_priority_speak(pid)


@pytest.mark.asyncio
async def test_open_floor_cooldown_uses_legacy_formula():
    """Open-Floor 沿用既有 _compute_proactive_cooldown 公式。"""
    pid = uuid4()
    policy = OpenFloorPolicy(pid)

    # All-AI mode, no recent chat → supervisor=40, crew=25*0.3=7.5
    ctx = _ctx(my_seat="supervisor")
    cd_sup = await policy.compute_cooldown(
        "supervisor", ctx, is_supervisor=True
    )
    assert cd_sup == pytest.approx(40.0, abs=0.1)

    cd_crew = await policy.compute_cooldown(
        "crew_1", _ctx(my_seat="crew_1"), is_supervisor=False
    )
    assert cd_crew == pytest.approx(7.5, abs=0.1)


def test_open_floor_system_prompt_mentions_yield_to_human():
    text = OpenFloorPolicy(uuid4()).system_prompt_fragment()
    assert "搶答" in text
    assert "禮讓" in text


# ---------------------------------------------------------------------------
# crew-silence 修（盲測 2026-06-09）：cued fragment 對「已開放發言的 crew」給主動分享許可
# ---------------------------------------------------------------------------


def test_cued_fragment_default_silences_uninvited_crew():
    """無 context（向下相容）/ 一般情況 → 維持沉默觀察文案。"""
    assert "保持沉默" in CuedPolicy(uuid4()).system_prompt_fragment()


def test_cued_fragment_opens_floor_to_crew_on_deadlock():
    """死結破除：組長講過、crew 全沒講、無明確點名 → crew fragment 改為主動分享許可。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(
        my_seat="crew_1",
        sub_phase="1.1b",
        recent_chat=[{"sender_id": "agent_supervisor", "content": "進入發現階段"}],
    )
    frag = policy.system_prompt_fragment(ctx)
    assert "主動分享" in frag
    assert "保持沉默" not in frag


def test_cued_fragment_keeps_silence_when_other_crew_invited():
    """有明確點名給別人 → 未被點名 crew 維持沉默（不破壞 cued 嚴格點名語意）。"""
    policy = CuedPolicy(uuid4())
    ctx = _ctx(
        my_seat="crew_1",
        sub_phase="1.1b",
        invited="crew_2",
        recent_chat=[{"sender_id": "agent_supervisor", "content": "換 crew_2"}],
    )
    frag = policy.system_prompt_fragment(ctx)
    assert "保持沉默" in frag
    assert "主動分享" not in frag
