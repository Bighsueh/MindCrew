"""Phase 35: supervisor.dedup helper unit tests (spec/16 §6.5.5)."""

from __future__ import annotations

import uuid

import pytest

from app.agents.supervisor.dedup import (
    get_fired_triggers,
    mark_trigger_fired,
    reset_fired_triggers,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_returns_empty_when_no_data() -> None:
    pid = uuid.uuid4()
    fired = await get_fired_triggers(pid, "1.1a")
    assert fired == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mark_then_get_returns_trigger() -> None:
    pid = uuid.uuid4()
    await mark_trigger_fired(pid, "1.1a", "B3a_halfway_pivot")
    fired = await get_fired_triggers(pid, "1.1a")
    assert "B3a_halfway_pivot" in fired
    await reset_fired_triggers(pid)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mark_is_idempotent() -> None:
    pid = uuid.uuid4()
    await mark_trigger_fired(pid, "1.1a", "B3a_halfway_pivot")
    await mark_trigger_fired(pid, "1.1a", "B3a_halfway_pivot")
    fired = await get_fired_triggers(pid, "1.1a")
    assert fired == {"B3a_halfway_pivot"}
    await reset_fired_triggers(pid)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_different_sub_phases_isolated() -> None:
    pid = uuid.uuid4()
    await mark_trigger_fired(pid, "1.1a", "B3a_halfway_pivot")
    await mark_trigger_fired(pid, "1.1b", "B3b_two_thirds_focus")
    fired_a = await get_fired_triggers(pid, "1.1a")
    fired_b = await get_fired_triggers(pid, "1.1b")
    assert fired_a == {"B3a_halfway_pivot"}
    assert fired_b == {"B3b_two_thirds_focus"}
    await reset_fired_triggers(pid)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reset_specific_sub_phase() -> None:
    pid = uuid.uuid4()
    await mark_trigger_fired(pid, "1.1a", "B3a_halfway_pivot")
    await mark_trigger_fired(pid, "1.1b", "B3b_two_thirds_focus")
    await reset_fired_triggers(pid, sub_phase="1.1a")
    assert await get_fired_triggers(pid, "1.1a") == set()
    assert await get_fired_triggers(pid, "1.1b") == {"B3b_two_thirds_focus"}
    await reset_fired_triggers(pid)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reset_all_for_project() -> None:
    pid = uuid.uuid4()
    await mark_trigger_fired(pid, "1.1a", "B3a_halfway_pivot")
    await mark_trigger_fired(pid, "1.1b", "B3c_close_diverge")
    await reset_fired_triggers(pid, sub_phase=None)
    assert await get_fired_triggers(pid, "1.1a") == set()
    assert await get_fired_triggers(pid, "1.1b") == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_sub_phase_safe() -> None:
    pid = uuid.uuid4()
    # 邊界：sub_phase=None 不該炸
    fired = await get_fired_triggers(pid, None)
    assert fired == set()
    await mark_trigger_fired(pid, None, "B3a_halfway_pivot")  # no-op
    await mark_trigger_fired(pid, "1.1a", "")  # no-op
    assert await get_fired_triggers(pid, "1.1a") == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deferred_a_dedup_marked_when_b_wins(monkeypatch) -> None:
    """Phase 42（router 餓死防呆）：B 贏時被擠到 pending 的 A——dedup-eligible（A1 進場宣布）
    要立即標記 fired，否則每 tick 重新偵測＋重新入列、pending_a 無限膨脹、A1 永遠輪不到。"""
    from app.agents.supervisor import router

    pid = uuid.uuid4()
    await reset_fired_triggers(pid)

    async def fake_a(ctx):
        return [("A1_phase_enter_announce", {"sub_phase": "1.1a",
                "sub_phase_name": "經驗分享", "divergence_or_convergence": "發散"})]

    async def fake_b(ctx):
        return [("B13_share_invite_next", {"next_crew_name": "小美",
                "next_crew_seat": "crew_2", "remaining": "2"})]

    monkeypatch.setattr(router, "detect_a_triggers", fake_a)
    monkeypatch.setattr(router, "detect_b_triggers", fake_b)

    decision = await router.select_supervisor_persona(pid, {"current_sub_phase": "1.1a"})
    assert decision.persona is not None and decision.persona.persona == "B"  # B 優先
    fired = await get_fired_triggers(pid, "1.1a")
    assert "A1_phase_enter_announce" in fired  # 被擠掉的 A1 已標記 → 不會每 tick 重入列
    await reset_fired_triggers(pid)
