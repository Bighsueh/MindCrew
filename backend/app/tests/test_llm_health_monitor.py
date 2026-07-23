"""LLM health monitor 狀態機測試（Phase 42 D5 / G14, spec 20 §13.2）。

純邏輯、無 DB：mock fail_stop 編排（on_llm_down/on_llm_recovered）與 provider
健康檢查（ProviderRegistry.get_entries）。涵蓋：
  * reactive 連續達門檻判 down／2 不觸發／任一成功歸零
  * proactive 連續全 unhealthy 判 down／任一健康恢復
  * 「down 期間 agent 停呼叫→只能靠 proactive 恢復」的關鍵路徑
  * 轉換 idempotent（並發只觸發一次）
  * snapshot 形狀
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.health_monitor import health_monitor


@pytest.fixture(autouse=True)
def _reset_and_patch(monkeypatch):
    """每測試重置單例＋以 AsyncMock 取代 fail_stop 編排（記錄 down/up 呼叫）。"""
    health_monitor.reset()
    down = AsyncMock()
    up = AsyncMock()
    monkeypatch.setattr("app.llm.fail_stop.on_llm_down", down)
    monkeypatch.setattr("app.llm.fail_stop.on_llm_recovered", up)
    yield SimpleNamespace(down=down, up=up)
    health_monitor.reset()


def _fake_entry(name: str, healthy: bool):
    inst = SimpleNamespace(health_check=AsyncMock(return_value=healthy))
    row = SimpleNamespace(id=uuid4(), name=name)
    return SimpleNamespace(row=row, instance=inst)


def _patch_entries(monkeypatch, entries):
    async def _get_entries(*_a, **_k):
        return entries

    monkeypatch.setattr(
        "app.llm.registry.ProviderRegistry.get_entries", _get_entries
    )


# ── reactive ─────────────────────────────────────────────────────────────


async def test_reactive_two_failures_not_down(_reset_and_patch):
    await health_monitor.record_exhaustion("boom")
    await health_monitor.record_exhaustion("boom")
    assert health_monitor.is_down() is False
    _reset_and_patch.down.assert_not_called()


async def test_reactive_three_failures_trips_down(_reset_and_patch):
    for _ in range(3):
        await health_monitor.record_exhaustion("boom")
    assert health_monitor.is_down() is True
    _reset_and_patch.down.assert_awaited_once()


async def test_reactive_success_resets_counter(_reset_and_patch):
    await health_monitor.record_exhaustion("boom")
    await health_monitor.record_exhaustion("boom")
    await health_monitor.record_success()
    assert health_monitor.is_down() is False
    # 歸零後需重新累積 3 次才 down
    await health_monitor.record_exhaustion("boom")
    await health_monitor.record_exhaustion("boom")
    assert health_monitor.is_down() is False
    _reset_and_patch.down.assert_not_called()


async def test_reactive_recovery_calls_resume(_reset_and_patch):
    for _ in range(3):
        await health_monitor.record_exhaustion("boom")
    assert health_monitor.is_down() is True
    await health_monitor.record_success()
    assert health_monitor.is_down() is False
    _reset_and_patch.up.assert_awaited_once()


async def test_concurrent_exhaustions_trigger_down_once(_reset_and_patch):
    import asyncio

    await asyncio.gather(
        *[health_monitor.record_exhaustion("boom") for _ in range(10)]
    )
    assert health_monitor.is_down() is True
    # 並發多次失敗只觸發一次 fail-stop 編排
    _reset_and_patch.down.assert_awaited_once()


# ── proactive ────────────────────────────────────────────────────────────


async def test_proactive_all_unhealthy_trips_down(monkeypatch, _reset_and_patch):
    _patch_entries(monkeypatch, [_fake_entry("a", False), _fake_entry("b", False)])
    await health_monitor.run_health_check_once()
    await health_monitor.run_health_check_once()
    assert health_monitor.is_down() is False
    await health_monitor.run_health_check_once()
    assert health_monitor.is_down() is True
    _reset_and_patch.down.assert_awaited_once()
    snap = health_monitor.snapshot()
    assert snap["overall_status"] == "down"
    assert all(p["healthy"] is False for p in snap["providers"])


async def test_proactive_any_healthy_keeps_up(monkeypatch, _reset_and_patch):
    _patch_entries(monkeypatch, [_fake_entry("a", False), _fake_entry("b", True)])
    for _ in range(5):
        await health_monitor.run_health_check_once()
    assert health_monitor.is_down() is False
    _reset_and_patch.down.assert_not_called()


async def test_proactive_recovery_after_down(monkeypatch, _reset_and_patch):
    bad = [_fake_entry("a", False), _fake_entry("b", False)]
    _patch_entries(monkeypatch, bad)
    for _ in range(3):
        await health_monitor.run_health_check_once()
    assert health_monitor.is_down() is True

    good = [_fake_entry("a", True), _fake_entry("b", True)]
    _patch_entries(monkeypatch, good)
    await health_monitor.run_health_check_once()
    assert health_monitor.is_down() is False
    _reset_and_patch.up.assert_awaited_once()


async def test_proactive_recovers_reactive_down(monkeypatch, _reset_and_patch):
    """關鍵路徑：reactive 判 down 後 agent 停呼叫 → 只能靠 proactive 健檢恢復。"""
    for _ in range(3):
        await health_monitor.record_exhaustion("boom")
    assert health_monitor.is_down() is True

    _patch_entries(monkeypatch, [_fake_entry("a", True)])
    await health_monitor.run_health_check_once()
    assert health_monitor.is_down() is False
    _reset_and_patch.up.assert_awaited_once()


async def test_no_providers_not_down(monkeypatch, _reset_and_patch):
    _patch_entries(monkeypatch, [])
    for _ in range(5):
        await health_monitor.run_health_check_once()
    assert health_monitor.is_down() is False
    _reset_and_patch.down.assert_not_called()


# ── snapshot ─────────────────────────────────────────────────────────────


async def test_snapshot_shape(monkeypatch, _reset_and_patch):
    _patch_entries(monkeypatch, [_fake_entry("p1", True)])
    await health_monitor.run_health_check_once()
    snap = health_monitor.snapshot()
    assert set(snap) == {
        "overall_status",
        "reactive_consecutive_failures",
        "reactive_threshold",
        "proactive_unhealthy_streak",
        "proactive_threshold",
        "last_status_change",
        "providers",
    }
    assert snap["overall_status"] == "up"
    assert snap["reactive_threshold"] == 3
    (p,) = snap["providers"]
    assert set(p) == {
        "provider_id",
        "provider_name",
        "healthy",
        "consecutive_failures",
        "last_failure_at",
        "last_failure_reason",
        "last_check_at",
        "cooldown_remaining_seconds",
    }
    assert p["provider_name"] == "p1"
    assert p["healthy"] is True
