"""房間休眠/喚醒編排測試（Phase 43, spec 20 §3/§11.7）。

純邏輯、無 DB：mock TimerService.get_state/pause/resume、seat_manager
stop/start_all_agents、event_bus.publish、_set_status。驗證——
  * suspend_room 只暫停未暫停房（reason=awaiting_human）＋停 agent＋設 suspended＋room_paused
  * suspend_room 遇已暫停房（teacher/llm_down/已 awaiting_human）no-op（不覆蓋）
  * resume_room 只解凍 awaiting_human 房（resume＋起 agent＋設 active＋room_resumed）
  * resume_room 遇 teacher/llm_down/未暫停 no-op（老師仍握控制權）
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents import room_hibernation
from app.timer.schemas import TimerState


def _running() -> TimerState:
    return TimerState()


def _paused(reason: str) -> TimerState:
    return TimerState(paused_at="2026-06-20T00:00:00+00:00", pause_reason=reason)


@pytest.fixture
def _mocks(monkeypatch):
    get_state = AsyncMock()
    pause = AsyncMock()
    resume = AsyncMock()
    stop_all = AsyncMock()
    start_all = AsyncMock()
    publish = AsyncMock()
    set_status = AsyncMock()
    monkeypatch.setattr("app.timer.service.TimerService.get_state", get_state)
    monkeypatch.setattr("app.timer.service.TimerService.pause", pause)
    monkeypatch.setattr("app.timer.service.TimerService.resume", resume)
    monkeypatch.setattr("app.seats.manager.seat_manager.stop_all_agents", stop_all)
    monkeypatch.setattr("app.seats.manager.seat_manager.start_all_agents", start_all)
    monkeypatch.setattr("app.events.bus.event_bus.publish", publish)
    monkeypatch.setattr(room_hibernation, "_set_status", set_status)
    return {
        "get_state": get_state,
        "pause": pause,
        "resume": resume,
        "stop_all": stop_all,
        "start_all": start_all,
        "publish": publish,
        "set_status": set_status,
    }


async def test_suspend_running_room(_mocks):
    pid = uuid4()
    _mocks["get_state"].return_value = _running()

    await room_hibernation.suspend_room(pid)

    _mocks["pause"].assert_awaited_once_with(pid, reason="awaiting_human")
    _mocks["set_status"].assert_awaited_once_with(pid, "suspended")
    _mocks["stop_all"].assert_awaited_once_with(pid)
    assert _mocks["publish"].await_count == 1
    event = _mocks["publish"].await_args.args[0]
    assert event.type == "room_paused"
    assert event.reason == "awaiting_human"
    assert event.project_id == pid


@pytest.mark.parametrize("reason", ["teacher", "llm_down", "awaiting_human"])
async def test_suspend_noop_when_already_paused(_mocks, reason):
    pid = uuid4()
    _mocks["get_state"].return_value = _paused(reason)

    await room_hibernation.suspend_room(pid)

    _mocks["pause"].assert_not_awaited()
    _mocks["set_status"].assert_not_awaited()
    _mocks["stop_all"].assert_not_awaited()
    _mocks["publish"].assert_not_awaited()


async def test_suspend_noop_when_no_state(_mocks):
    pid = uuid4()
    _mocks["get_state"].return_value = None

    await room_hibernation.suspend_room(pid)

    _mocks["pause"].assert_not_awaited()
    _mocks["publish"].assert_not_awaited()


async def test_resume_awaiting_human_room(_mocks):
    pid = uuid4()
    _mocks["get_state"].return_value = _paused("awaiting_human")

    await room_hibernation.resume_room(pid)

    _mocks["set_status"].assert_awaited_once_with(pid, "active")
    _mocks["resume"].assert_awaited_once_with(pid)
    _mocks["start_all"].assert_awaited_once_with(pid)
    assert _mocks["publish"].await_count == 1
    event = _mocks["publish"].await_args.args[0]
    assert event.type == "room_resumed"
    assert event.project_id == pid


@pytest.mark.parametrize("reason", ["teacher", "llm_down"])
async def test_resume_noop_when_other_pause_reason(_mocks, reason):
    pid = uuid4()
    _mocks["get_state"].return_value = _paused(reason)

    await room_hibernation.resume_room(pid)

    _mocks["resume"].assert_not_awaited()
    _mocks["set_status"].assert_not_awaited()
    _mocks["start_all"].assert_not_awaited()
    _mocks["publish"].assert_not_awaited()


async def test_resume_noop_when_running(_mocks):
    pid = uuid4()
    _mocks["get_state"].return_value = _running()

    await room_hibernation.resume_room(pid)

    _mocks["resume"].assert_not_awaited()
    _mocks["publish"].assert_not_awaited()


# ── Phase 42 補正 R4：D5 縫 (a) ＋ 裁定⑤ round_lock TTL 續期 ─────────────────


class _FakeSubPhaseSession:
    """resume_room 內 DB 讀 current_sub_phase 的替身。"""

    def __init__(self, sub_phase: str | None = "2.2") -> None:
        self._sub = sub_phase

    async def scalar(self, *_a, **_k):
        return self._sub

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def test_resume_during_llm_outage_repauses_llm_down(monkeypatch, _mocks):
    """D5 縫 (a)：LLM 判定 down 期間人回來——喚醒照做但立即 llm_down 重新暫停＋banner，
    不留下「房醒了、agent 全靜默」的假活狀態。"""
    pid = uuid4()
    _mocks["get_state"].return_value = _paused("awaiting_human")
    monkeypatch.setattr(
        "app.db.session.async_session_factory", lambda: _FakeSubPhaseSession()
    )
    monkeypatch.setattr("app.agents.round_lock.refresh_ttl", AsyncMock())
    monkeypatch.setattr(
        "app.llm.health_monitor.health_monitor.is_down", lambda: True
    )

    await room_hibernation.resume_room(pid)

    _mocks["resume"].assert_awaited_once_with(pid)
    _mocks["pause"].assert_awaited_once_with(pid, reason="llm_down")
    types = [c.args[0].type for c in _mocks["publish"].await_args_list]
    assert "room_resumed" in types and "room_paused" in types


async def test_resume_refreshes_round_lock_ttl(monkeypatch, _mocks):
    """裁定⑤：喚醒時把本關回合鎖鍵續期（休眠可超過 1 小時，防 round/參與歸零）。"""
    pid = uuid4()
    _mocks["get_state"].return_value = _paused("awaiting_human")
    monkeypatch.setattr(
        "app.db.session.async_session_factory", lambda: _FakeSubPhaseSession("2.6")
    )
    refresh = AsyncMock()
    monkeypatch.setattr("app.agents.round_lock.refresh_ttl", refresh)
    monkeypatch.setattr(
        "app.llm.health_monitor.health_monitor.is_down", lambda: False
    )

    await room_hibernation.resume_room(pid)

    refresh.assert_awaited_once_with(pid, "2.6")
    _mocks["pause"].assert_not_awaited()  # LLM 健康 → 不重新暫停
