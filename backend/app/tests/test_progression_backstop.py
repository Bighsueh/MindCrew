"""Progression watcher 兜底語意（Phase 42 A1，spec 04-06 §5.8 v4.25）。

取代 test_progression_overtime_safety_valve.py（floor/雙閥/教師 hold 已移除）。
鎖定新模型的兩條兜底路徑與「常態不代推」：

  (a) time-box 100%：組長健在 → 寬限內不代推；寬限過（或組長失能）→ 樣板強推
      （skip_gate_check=True，時間到＝最終覆蓋）。
  (b) 組長失能 + 訊號已達成 → 代推（gate 照常）；訊號未達成 → 等 time-box。
  常態（<100%、組長健在）→ watcher 完全不動，即使 ready（推進權在組長）。
  暖場（macro=warmup）→ watcher 不兜（Evaluator._evaluate_warmup 負責）。

全部以 mock 取代 DB / timer / redis（沿用 test_progression_warmup_gate.py 風格）。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.progression import watcher as w
from app.progression import supervisor_activity as sa
from app.stages.sub_phases import get_sub_phase
from app.timer import service as timer_service
from app.timer import calculator as timer_calc

# 1.1b：硬格（min_artifact_counts）、非 micro 末格；1.1d：micro 1.1 末格。
_HARD_SUB = "1.1b"
_WARMUP_SUB = "0.0a"


def _patch_stall(stalled: bool):
    return patch.object(sa, "supervisor_stalled", new=AsyncMock(return_value=stalled))


@pytest.mark.asyncio
async def test_normal_path_watcher_does_not_advance_even_when_ready() -> None:
    """<100% + 組長健在 → 不代推（即使 ready）——常態推進權在組長。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=50.0)),
        patch.object(w, "_is_ready", new=AsyncMock(return_value=True)),
        _patch_stall(False),
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, _HARD_SUB)
    adv.assert_not_awaited()


@pytest.mark.asyncio
async def test_supervisor_stall_with_ready_advances_early() -> None:
    """兜底 (b)：組長失能 + 訊號達成 → <100% 即代推（gate 照常檢查）。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=40.0)),
        patch.object(w, "_is_ready", new=AsyncMock(return_value=True)),
        _patch_stall(True),
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, _HARD_SUB)
    adv.assert_awaited_once()
    args = adv.call_args.args
    kwargs = adv.call_args.kwargs
    assert args[0] == pid and args[1] == _HARD_SUB
    assert kwargs.get("reason") == "supervisor_stall"
    assert kwargs.get("skip_gate_check") is not True  # gate 照常


@pytest.mark.asyncio
async def test_supervisor_stall_not_ready_waits_for_timebox() -> None:
    """兜底 (b) 反向：組長失能但訊號未達成 → 不提前代推（等 time-box）。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=40.0)),
        patch.object(w, "_is_ready", new=AsyncMock(return_value=False)),
        _patch_stall(True),
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, _HARD_SUB)
    adv.assert_not_awaited()


@pytest.mark.asyncio
async def test_timebox_within_grace_holds_for_supervisor_closure() -> None:
    """兜底 (a)：100% 到、組長健在、仍在寬限內 → 給組長自己誠實收尾，不代推。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=101.0)),
        _patch_stall(False),
        patch.object(
            w, "_overtime_seconds",
            new=AsyncMock(return_value=w._TIMEBOX_GRACE_SECONDS - 10.0),
        ),
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, _HARD_SUB)
    adv.assert_not_awaited()


@pytest.mark.asyncio
async def test_timebox_grace_expired_forces_template_advance() -> None:
    """兜底 (a)：寬限過了組長仍沒收尾 → 樣板強推（skip_gate_check=True）。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=120.0)),
        _patch_stall(False),
        patch.object(
            w, "_overtime_seconds",
            new=AsyncMock(return_value=w._TIMEBOX_GRACE_SECONDS + 5.0),
        ),
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, _HARD_SUB)
    adv.assert_awaited_once()
    kwargs = adv.call_args.kwargs
    assert kwargs.get("reason") == "time_box"
    assert kwargs.get("skip_gate_check") is True


@pytest.mark.asyncio
async def test_timebox_with_stalled_supervisor_skips_grace() -> None:
    """兜底 (a)：100% 到且組長已失能 → 不等寬限直接強推。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=100.0)),
        _patch_stall(True),
        patch.object(w, "_overtime_seconds", new=AsyncMock(return_value=0.0)) as ot,
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, _HARD_SUB)
    adv.assert_awaited_once()
    assert adv.call_args.kwargs.get("reason") == "time_box"
    ot.assert_not_awaited()  # 失能時不需要算寬限


@pytest.mark.asyncio
async def test_warmup_backstop_requires_hard_limit_and_stall() -> None:
    """暖場兜底＝雙條件（Phase 42 B1，spec 28 §5.4）：硬上限到但組長健在 → 不代推。

    完整暖場兜底矩陣見 test_warmup_stage.py::TestWarmupWatcherBackstop。
    """
    assert get_sub_phase(_WARMUP_SUB).macro_stage == "warmup"
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=150.0)),
        _patch_stall(False),
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, _WARMUP_SUB)
    adv.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_timer_no_advance() -> None:
    """沒有 timer（used_pct 不可得）→ 不推進（等教師啟用計時器）。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=None)),
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, _HARD_SUB)
    adv.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_project_skipped() -> None:
    """stage=completed 的專案（sub_phase 停末格、time-box 永久 100%）→ 直接跳過，
    不每 tick 觸發 CAS noop 重試（live 2026-06-11 抓到的洗 log 迴圈）。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=200.0)) as up,
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, "2.7", current_stage="completed")
    adv.assert_not_awaited()
    up.assert_not_awaited()


@pytest.mark.asyncio
async def test_boundary_cell_also_backstopped() -> None:
    """micro 末格（如 1.1d）同樣被兜底——watcher 不再跳過邊界格（經三層路由）。"""
    pid = uuid4()
    with (
        patch.object(w, "_get_used_pct", new=AsyncMock(return_value=130.0)),
        _patch_stall(True),
        patch.object(w, "_advance", new=AsyncMock()) as adv,
    ):
        await w._check_one(pid, "1.1d")
    adv.assert_awaited_once()
    assert adv.call_args.args[1] == "1.1d"


# ── Phase 42 D1d Bug②：寬限天花板修正（_overtime_seconds 改絕對秒數）──────────
#
# 根因：get_used_pct 在 200% 封頂（service.py:245），舊 _overtime_seconds 用
# (used_pct-100)/100*budget 反推 → overtime 最多＝budget。短格（budget < 寬限
# 90s，如 2.7=60s／2.5=60s）的 overtime 被天花板鎖死、永遠到不了寬限 → 巨觀
# time-box 逃生（define→completed）不可達、2.7 永遠 thrash（live 2026-06-15 坐實）。
# 修法：改讀絕對 used 秒數（TimerService.get_used_seconds，不受 cap）回 used-budget。


def _patch_overtime_deps(budget, used):
    """patch _overtime_seconds 的三個依賴（get_config / get_phase_budget_seconds /
    get_used_seconds）。budget 走 calculator（同步）、used 走 TimerService（async）。"""
    return (
        patch.object(
            timer_service.TimerService, "get_config",
            new=AsyncMock(return_value=object()),
        ),
        patch.object(timer_calc, "get_phase_budget_seconds", return_value=budget),
        patch.object(
            timer_service.TimerService, "get_used_seconds",
            new=AsyncMock(return_value=used),
        ),
    )


@pytest.mark.asyncio
async def test_overtime_absolute_short_budget_reaches_grace() -> None:
    """短格（budget 60s < 寬限 90s）：已用 150s → overtime=90s ≥ 寬限。

    舊算法（used_pct 封頂 200%）只給 (200-100)/100*60=60s < 90s → 永遠卡死。
    這是 2.7/2.5 巨觀逃生不可達的回歸守衛。"""
    pid = uuid4()
    p_cfg, p_budget, p_used = _patch_overtime_deps(budget=60, used=150)
    with p_cfg, p_budget, p_used:
        ot = await w._overtime_seconds(pid, "2.7")
    assert ot == 90.0
    assert ot >= w._TIMEBOX_GRACE_SECONDS  # 能真正觸發逃生


@pytest.mark.asyncio
async def test_overtime_absolute_large_budget_unchanged() -> None:
    """大格回歸：budget 600s、已用 690s → overtime=90s（與舊百分比算法一致，
    cap 未咬到大格，故行為不變）。"""
    pid = uuid4()
    p_cfg, p_budget, p_used = _patch_overtime_deps(budget=600, used=690)
    with p_cfg, p_budget, p_used:
        ot = await w._overtime_seconds(pid, "1.1b")
    assert ot == 90.0


@pytest.mark.asyncio
async def test_overtime_none_when_used_seconds_unreadable() -> None:
    """used 秒數讀不到（timer 未起算）→ None（保守不代推，不誤觸 skip-gate）。"""
    pid = uuid4()
    p_cfg, p_budget, p_used = _patch_overtime_deps(budget=60, used=None)
    with p_cfg, p_budget, p_used:
        ot = await w._overtime_seconds(pid, "2.7")
    assert ot is None


@pytest.mark.asyncio
async def test_overtime_none_when_budget_missing() -> None:
    """預算不可得（0/None）→ None（沿用舊保守語意）。"""
    pid = uuid4()
    p_cfg, p_budget, p_used = _patch_overtime_deps(budget=0, used=150)
    with p_cfg, p_budget, p_used:
        ot = await w._overtime_seconds(pid, "2.7")
    assert ot is None


@pytest.mark.asyncio
async def test_overtime_never_negative_below_budget() -> None:
    """已用 < budget（未到 time-box，理論上不會被呼叫）→ 夾到 0、不回負數。"""
    pid = uuid4()
    p_cfg, p_budget, p_used = _patch_overtime_deps(budget=60, used=30)
    with p_cfg, p_budget, p_used:
        ot = await w._overtime_seconds(pid, "2.7")
    assert ot == 0.0
