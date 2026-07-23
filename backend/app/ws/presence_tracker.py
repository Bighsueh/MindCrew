"""Human Presence Gate — tracks whether real humans are connected to each project.

AI agents block on ``get_presence_event(project_id).wait()`` and resume
instantly when the event is set (i.e. at least one human is connected).

A 30-second grace period prevents flapping on brief disconnects (tab refresh,
network blip).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable
from uuid import UUID

logger = logging.getLogger(__name__)

# Grace period before pausing agents after the last human disconnects.
_GRACE_PERIOD_SECONDS = 30.0

# Phase 43：present↔absent 轉換時觸發的 async hook（接 room_hibernation）。
PresenceHook = Callable[[UUID], Awaitable[None]]


class PresenceTracker:
    """Singleton that maps project_id → human connection count + asyncio.Event."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._grace_timers: dict[str, asyncio.Task[None]] = {}
        # Phase 43：在席轉換 hook（休眠/喚醒編排）；None＝未註冊。
        self._on_absent: PresenceHook | None = None
        self._on_present: PresenceHook | None = None
        # 持有 fire-and-forget hook task 參考，避免被 GC 中途回收。
        self._hook_tasks: set[asyncio.Task[None]] = set()

    def set_presence_hooks(
        self,
        *,
        on_absent: PresenceHook | None = None,
        on_present: PresenceHook | None = None,
    ) -> None:
        """註冊在席轉換 hook（main.py 啟動時接 room_hibernation 的 suspend/resume）。

        - ``on_present``：absent→present（人重連）→ 喚醒休眠房。
        - ``on_absent``：present→absent（grace 後離席）→ 全房休眠。
        兩者皆須為 idempotent / 自帶守則（resume 只解凍 awaiting_human、suspend 遇
        已暫停 no-op），因為 hook 會在每次轉換時觸發（含正常開房/關房）。
        """
        self._on_absent = on_absent
        self._on_present = on_present

    def _fire_hook(self, hook: PresenceHook | None, key: str) -> None:
        """以 fire-and-forget task 觸發 hook（key＝str(project_id)）。"""
        if hook is None:
            return

        def _done(task: asyncio.Task[None]) -> None:
            self._hook_tasks.discard(task)
            if not task.cancelled() and task.exception() is not None:
                logger.error(
                    "presence hook failed project=%s: %r", key, task.exception()
                )

        try:
            task = asyncio.create_task(hook(UUID(key)))
            self._hook_tasks.add(task)
            task.add_done_callback(_done)
        except RuntimeError:
            # 無 running loop（理論上不會：connect / grace 皆在 event loop 內）。
            logger.debug("presence hook skipped (no running loop) project=%s", key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_human_connect(self, project_id: UUID) -> None:
        """Call when a human WebSocket connection is established."""
        key = str(project_id)

        # Cancel any pending grace-period timer
        timer = self._grace_timers.pop(key, None)
        if timer is not None and not timer.done():
            timer.cancel()

        prev = self._counts.get(key, 0)
        self._counts[key] = prev + 1

        event = self._get_or_create_event(key)
        if not event.is_set():
            event.set()
            logger.info(
                "Project %s human presence: absent → present (count=%d)",
                key,
                self._counts[key],
            )
            # Phase 43：人重連 → 喚醒休眠房（resume_room 自帶守則，非休眠房 no-op）。
            self._fire_hook(self._on_present, key)
        else:
            logger.debug(
                "Project %s human connect (count=%d)", key, self._counts[key]
            )

    def on_human_disconnect(self, project_id: UUID) -> None:
        """Call when a human WebSocket connection is closed."""
        key = str(project_id)
        current = self._counts.get(key, 0)
        if current <= 0:
            logger.warning(
                "Project %s disconnect with count already 0 — ignoring", key
            )
            return

        self._counts[key] = current - 1
        logger.debug(
            "Project %s human disconnect (count=%d)", key, self._counts[key]
        )

        if self._counts[key] == 0:
            # Start the grace-period timer
            self._grace_timers[key] = self._start_grace_timer(key)

    def get_presence_event(self, project_id: UUID) -> asyncio.Event:
        """Return the presence event for *project_id* (creates if needed).

        New events start **cleared** (agents will wait until a human connects).
        """
        return self._get_or_create_event(str(project_id))

    def is_human_present(self, project_id: UUID) -> bool:
        """One-shot check — ``True`` when at least one human is connected."""
        return self._counts.get(str(project_id), 0) > 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_or_create_event(self, key: str) -> asyncio.Event:
        event = self._events.get(key)
        if event is None:
            event = asyncio.Event()
            # Default: cleared (safe — agents wait for a human)
            self._events[key] = event
        return event

    def _start_grace_timer(self, key: str) -> asyncio.Task[None]:
        """Create a grace-period task that clears the event after the delay.

        Uses a closure to capture the task reference so that stale timers
        (replaced by a newer timer under the same key) are harmlessly ignored.
        """
        task: asyncio.Task[None] | None = None

        async def _run() -> None:
            try:
                await asyncio.sleep(_GRACE_PERIOD_SECONDS)
            except asyncio.CancelledError:
                return

            # Double-check nobody reconnected while we slept
            if self._counts.get(key, 0) > 0:
                return

            # Only act if we are still the active timer for this key
            if self._grace_timers.get(key) is not task:
                return

            event = self._events.get(key)
            if event is not None and event.is_set():
                event.clear()
                logger.info("Project %s human presence: present → absent", key)
                # Phase 43：離席（grace 後）→ 全房休眠（suspend_room 遇已暫停 no-op）。
                self._fire_hook(self._on_absent, key)

            self._grace_timers.pop(key, None)

        task = asyncio.create_task(_run())
        return task


# Module-level singleton
presence_tracker = PresenceTracker()
