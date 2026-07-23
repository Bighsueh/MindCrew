"""LLM health monitor — Phase 42 D5（G14／#35，spec 20 §13.2）。

兩個正交訊號判定 LLM「持續不可用（down）」：

* **Reactive（反應式）**：``factory.chat_completion`` 備援耗盡（所有 tier×class
  候選皆失敗）時計一次硬失敗；連續 ``LLM_DOWN_CONSECUTIVE_FAILURES`` 次 → down。
  任一次成功歸零。
* **Proactive（主動式）**：背景迴圈每 ``LLM_HEALTH_CHECK_INTERVAL_SECONDS`` 秒
  逐一 ping 各 provider；連續 N 次「全 provider 不健康」→ down。任一健康歸零，
  並用於**恢復偵測**——down 期間 agent 停止呼叫 LLM，reactive 等不到「成功」，
  恢復只能靠這條背景迴圈。

判定 down/up 變化時（``asyncio.Lock`` 守，並發只觸發一次）lazy import ``fail_stop``
做全房暫停／恢復編排。``is_down()`` 為 in-memory O(1)，供 agent 決策迴圈每 tick
快速查、零 DB。

本模組只管「健康狀態」，不認得 project／timer／events（編排在 ``fail_stop``）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

_SHUTDOWN = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderHealthState:
    """單一 provider 的健康快照（proactive 迴圈維護，供 admin 觀測）。"""

    def __init__(self, provider_id: str, name: str) -> None:
        self.provider_id = provider_id
        self.name = name
        self.healthy: bool = True
        self.consecutive_failures: int = 0
        self.last_failure_at: str | None = None
        self.last_failure_reason: str | None = None
        self.last_check_at: str | None = None

    def to_dict(self) -> dict:
        # cooldown 屬 router 的瞬時 per-provider 狀態（與全域 down 正交）；於快照時即時讀。
        from app.llm.router import ProviderRouter

        return {
            "provider_id": self.provider_id,
            "provider_name": self.name,
            "healthy": self.healthy,
            "consecutive_failures": self.consecutive_failures,
            "last_failure_at": self.last_failure_at,
            "last_failure_reason": self.last_failure_reason,
            "last_check_at": self.last_check_at,
            "cooldown_remaining_seconds": ProviderRouter.cooldown_remaining(
                self.provider_id
            ),
        }


class LLMHealthMonitor:
    """雙訊號健康判定單例。"""

    def __init__(self) -> None:
        self._reactive_failures = 0
        self._proactive_streak = 0
        self._is_down = False
        self._providers: dict[str, ProviderHealthState] = {}
        self._last_status_change: str | None = None
        self._transition_lock = asyncio.Lock()

    @property
    def _threshold(self) -> int:
        return max(1, settings.LLM_DOWN_CONSECUTIVE_FAILURES)

    # ── fast read（agent 迴圈每 tick 查）───────────────────────────────
    def is_down(self) -> bool:
        return self._is_down

    def _compute_down(self) -> bool:
        return (
            self._reactive_failures >= self._threshold
            or self._proactive_streak >= self._threshold
        )

    async def _reconcile_locked(self) -> None:
        """重算 down/up 並（變化時）跑暫停／恢復編排。

        **呼叫前必須持有 `self._transition_lock`**——所有計數寫入與這裡的讀取／轉換
        在同一把鎖內完成，read-modify-reconcile 原子化、並發只觸發一次（spec 20 §13）。
        """
        new_down = self._compute_down()
        if new_down == self._is_down:
            return
        self._is_down = new_down
        self._last_status_change = _now_iso()
        try:
            from app.llm import fail_stop

            if new_down:
                logger.warning(
                    "LLM judged DOWN (reactive=%d proactive=%d threshold=%d)"
                    " → fail-stop",
                    self._reactive_failures,
                    self._proactive_streak,
                    self._threshold,
                )
                await fail_stop.on_llm_down()
            else:
                logger.info("LLM recovered → resuming llm_down rooms")
                await fail_stop.on_llm_recovered()
        except Exception:
            logger.exception("fail-stop orchestration failed (down=%s)", new_down)

    # ── reactive 訊號（factory 呼叫）──────────────────────────────────
    async def record_exhaustion(self, error: str | None = None) -> None:
        """``factory`` 備援耗盡點呼叫：計一次硬失敗（計數＋轉換同鎖內原子完成）。"""
        async with self._transition_lock:
            self._reactive_failures += 1
            logger.warning(
                "LLM exhaustion recorded (consecutive=%d/%d): %s",
                self._reactive_failures,
                self._threshold,
                error,
            )
            await self._reconcile_locked()

    async def record_success(self) -> None:
        """任一 LLM 呼叫成功：連續計數歸零。穩態走 fast-path（lock-free int 讀取原子）。"""
        if (
            self._reactive_failures == 0
            and self._proactive_streak == 0
            and not self._is_down
        ):
            return
        async with self._transition_lock:
            self._reactive_failures = 0
            self._proactive_streak = 0
            await self._reconcile_locked()

    # ── proactive 訊號（背景迴圈）──────────────────────────────────────
    async def run_health_check_once(self) -> None:
        """ping 各 provider 一輪，更新 per-provider 健康＋全域 proactive streak。"""
        from app.llm.registry import ProviderRegistry

        try:
            entries = await ProviderRegistry.get_entries(force=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("health-check: registry load failed: %s", exc)
            return

        seen: set[str] = set()
        any_healthy = False
        for entry in entries:
            pid = str(entry.row.id)
            seen.add(pid)
            state = self._providers.setdefault(
                pid, ProviderHealthState(pid, entry.row.name)
            )
            state.name = entry.row.name
            state.last_check_at = _now_iso()
            ok = False
            reason: str | None = None
            try:
                ok = await entry.instance.health_check()
            except Exception as exc:  # noqa: BLE001
                ok = False
                reason = f"{type(exc).__name__}: {exc}"
            if ok:
                state.healthy = True
                state.consecutive_failures = 0
                any_healthy = True
            else:
                state.healthy = False
                state.consecutive_failures += 1
                state.last_failure_at = _now_iso()
                state.last_failure_reason = reason or "unhealthy"

        # 移除已不再設定的 provider 快照。
        for pid in list(self._providers):
            if pid not in seen:
                self._providers.pop(pid, None)

        if not entries:
            # 無 provider 設定＝無法服務，但屬設定問題（fail-stop 無益），不視為 outage。
            return

        # 穩態（全健康且計數皆 0、未 down）→ 免鎖直接返回。
        if any_healthy and not (
            self._reactive_failures or self._proactive_streak or self._is_down
        ):
            return

        # 計數寫入與轉換同鎖內完成（read-modify-reconcile 原子化）。
        async with self._transition_lock:
            if any_healthy:
                self._reactive_failures = 0
                self._proactive_streak = 0
            else:
                self._proactive_streak += 1
                logger.warning(
                    "health-check: all %d providers unhealthy (streak=%d/%d)",
                    len(entries),
                    self._proactive_streak,
                    self._threshold,
                )
            await self._reconcile_locked()

    async def background_loop(self) -> None:
        global _SHUTDOWN
        _SHUTDOWN = False
        interval = max(5, settings.LLM_HEALTH_CHECK_INTERVAL_SECONDS)
        logger.info("llm_health_monitor started (interval=%ds)", interval)
        while not _SHUTDOWN:
            try:
                await self.run_health_check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("llm_health_monitor tick failed")
            await asyncio.sleep(interval)
        logger.info("llm_health_monitor stopped")

    # ── admin 快照 ─────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        providers = [s.to_dict() for s in self._providers.values()]
        if self._is_down:
            overall = "down"
        elif (
            self._reactive_failures
            or self._proactive_streak
            or any(not p["healthy"] for p in providers)
        ):
            overall = "degraded"
        else:
            overall = "up"
        return {
            "overall_status": overall,
            "reactive_consecutive_failures": self._reactive_failures,
            "reactive_threshold": self._threshold,
            "proactive_unhealthy_streak": self._proactive_streak,
            "proactive_threshold": self._threshold,
            "last_status_change": self._last_status_change,
            "providers": providers,
        }

    # ── test helper ────────────────────────────────────────────────────
    def reset(self) -> None:
        self._reactive_failures = 0
        self._proactive_streak = 0
        self._is_down = False
        self._providers.clear()
        self._last_status_change = None


async def stop_llm_health_monitor() -> None:
    global _SHUTDOWN
    _SHUTDOWN = True


health_monitor = LLMHealthMonitor()
