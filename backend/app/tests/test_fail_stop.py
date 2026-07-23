"""LLM fail-stop 編排測試（Phase 42 D5 / G14, spec 20 §13.3/§13.4）。

純邏輯、無 DB：mock 房間清單（_active_rooms）、TimerService.pause/resume、
event_bus.publish。驗證——
  * on_llm_down 只暫停「未暫停」房，reason="llm_down"；老師手動 / 已 llm_down 暫停不碰
  * on_llm_recovered 只 resume pause_reason=="llm_down" 房；老師手動暫停不自動續跑
  * 單一房失敗被隔離、不影響其他房
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm import fail_stop


def _running():
    return {}


def _paused(reason: str):
    return {"paused_at": "2026-06-14T00:00:00+00:00", "pause_reason": reason}


@pytest.fixture
def _mocks(monkeypatch):
    pause = AsyncMock()
    resume = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr("app.timer.service.TimerService.pause", pause)
    monkeypatch.setattr("app.timer.service.TimerService.resume", resume)
    monkeypatch.setattr("app.events.bus.event_bus.publish", publish)
    return {"pause": pause, "resume": resume, "publish": publish}


def _patch_rooms(monkeypatch, rooms):
    async def _active_rooms():
        return rooms

    monkeypatch.setattr(fail_stop, "_active_rooms", _active_rooms)


async def test_on_llm_down_pauses_only_unpaused(monkeypatch, _mocks):
    running_id = uuid4()
    teacher_id = uuid4()
    already_id = uuid4()
    _patch_rooms(
        monkeypatch,
        [
            (running_id, _running()),
            (teacher_id, _paused("teacher")),
            (already_id, _paused("llm_down")),
        ],
    )
    await fail_stop.on_llm_down()

    # 只暫停 running 房，reason=llm_down
    _mocks["pause"].assert_awaited_once_with(running_id, reason="llm_down")
    # 廣播一次 room_paused（running 房）
    assert _mocks["publish"].await_count == 1
    event = _mocks["publish"].await_args.args[0]
    assert event.type == "room_paused"
    assert event.reason == "llm_down"
    assert event.project_id == running_id


async def test_on_llm_recovered_resumes_only_llm_down(monkeypatch, _mocks):
    llm_id = uuid4()
    teacher_id = uuid4()
    running_id = uuid4()
    _patch_rooms(
        monkeypatch,
        [
            (llm_id, _paused("llm_down")),
            (teacher_id, _paused("teacher")),
            (running_id, _running()),
        ],
    )
    await fail_stop.on_llm_recovered()

    _mocks["resume"].assert_awaited_once_with(llm_id)
    assert _mocks["publish"].await_count == 1
    event = _mocks["publish"].await_args.args[0]
    assert event.type == "room_resumed"
    assert event.project_id == llm_id


async def test_on_llm_down_isolates_per_room_failure(monkeypatch, _mocks):
    good_id = uuid4()
    bad_id = uuid4()

    async def _pause(project_id, reason="teacher"):
        if project_id == bad_id:
            raise RuntimeError("db blew up")

    _mocks["pause"].side_effect = _pause
    # bad 房排前面，good 房仍要被處理
    _patch_rooms(monkeypatch, [(bad_id, _running()), (good_id, _running())])

    await fail_stop.on_llm_down()  # 不應拋出

    assert _mocks["pause"].await_count == 2
    # good 房仍成功 publish（bad 房在 pause 階段就拋、不 publish）
    assert _mocks["publish"].await_count == 1
    assert _mocks["publish"].await_args.args[0].project_id == good_id


async def test_on_llm_down_noop_when_all_paused(monkeypatch, _mocks):
    _patch_rooms(
        monkeypatch,
        [(uuid4(), _paused("teacher")), (uuid4(), _paused("llm_down"))],
    )
    await fail_stop.on_llm_down()
    _mocks["pause"].assert_not_awaited()
    _mocks["publish"].assert_not_awaited()


# ── Phase 42 補正 R4（P1-7）：startup reconciliation ─────────────────────────


async def test_reconcile_on_startup_recovers_orphans_when_healthy(monkeypatch, _mocks):
    """重啟孤兒房收復：啟動健檢乾淨（overall=up）→ 補跑 on_llm_recovered。"""
    monkeypatch.setattr(
        "app.llm.health_monitor.health_monitor.run_health_check_once", AsyncMock()
    )
    monkeypatch.setattr(
        "app.llm.health_monitor.health_monitor.snapshot",
        lambda: {"overall_status": "up"},
    )
    recovered = AsyncMock()
    monkeypatch.setattr(fail_stop, "on_llm_recovered", recovered)
    await fail_stop.reconcile_on_startup()
    recovered.assert_awaited_once()


async def test_reconcile_on_startup_keeps_paused_when_degraded(monkeypatch, _mocks):
    """啟動健檢有失敗訊號（degraded/down）→ 不動，交背景 monitor 正常邊緣處理。"""
    monkeypatch.setattr(
        "app.llm.health_monitor.health_monitor.run_health_check_once", AsyncMock()
    )
    monkeypatch.setattr(
        "app.llm.health_monitor.health_monitor.snapshot",
        lambda: {"overall_status": "degraded"},
    )
    recovered = AsyncMock()
    monkeypatch.setattr(fail_stop, "on_llm_recovered", recovered)
    await fail_stop.reconcile_on_startup()
    recovered.assert_not_awaited()


async def test_reconcile_on_startup_skips_on_check_failure(monkeypatch, _mocks):
    """啟動健檢本身炸掉 → 保守不動（不誤 resume）。"""
    monkeypatch.setattr(
        "app.llm.health_monitor.health_monitor.run_health_check_once",
        AsyncMock(side_effect=RuntimeError("probe boom")),
    )
    recovered = AsyncMock()
    monkeypatch.setattr(fail_stop, "on_llm_recovered", recovered)
    await fail_stop.reconcile_on_startup()
    recovered.assert_not_awaited()
