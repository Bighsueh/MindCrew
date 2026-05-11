"""Timer watcher background loop — Spec 15 §4.2.

每 10 秒掃 active project：
  - 跨越 warning threshold (75/90/100%) → fire TimerWarningEvent
  - 100% + auto_advance → 呼叫 advance_sub_phase
  - 100% + !auto_advance → fire TimerTimeoutEvent（給 Stream D crew vote 聽）
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.db.models.project import Project
from app.db.session import async_session_factory
from app.timer.calculator import get_phase_budget_seconds
from app.timer.events import TimerTimeoutEvent, TimerWarningEvent
from app.timer.service import TimerService

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 10.0
_SHUTDOWN: bool = False


async def timer_watcher_loop() -> None:
    global _SHUTDOWN
    _SHUTDOWN = False
    logger.info("timer_watcher started (poll=%ds)", _POLL_INTERVAL_SECONDS)
    while not _SHUTDOWN:
        try:
            await _tick()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("timer_watcher tick failed")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    logger.info("timer_watcher stopped")


async def stop_timer_watcher() -> None:
    global _SHUTDOWN
    _SHUTDOWN = True


async def _tick() -> None:
    async with async_session_factory() as session:
        rows = await session.execute(
            select(Project).where(Project.status == "active")
        )
        projects = rows.scalars().all()

    for p in projects:
        try:
            await _check_one(p.id, p.current_sub_phase)
        except Exception:
            logger.debug("timer check project=%s failed", p.id, exc_info=True)


async def _check_one(project_id: UUID, current_sub_phase: str | None) -> None:
    if not current_sub_phase:
        return
    config = await TimerService.get_config(project_id)
    state = await TimerService.get_state(project_id)
    if config is None or state is None or state.current_sub_phase != current_sub_phase:
        return
    if state.is_paused():
        return

    used_secs = TimerService._compute_used_seconds(state)
    budget = get_phase_budget_seconds(config, current_sub_phase)
    if budget <= 0:
        return
    used_pct = used_secs / budget * 100.0

    # Fire warnings for crossed thresholds
    for threshold in config.warning_thresholds_pct:
        if used_pct >= threshold and threshold not in state.warnings_fired:
            fired = await TimerService.fire_warning(project_id, threshold)
            if fired:
                await _broadcast_warning(
                    project_id, threshold, current_sub_phase, used_secs, budget,
                )
                # 100% threshold: 觸發 timeout 流程
                if threshold == 100:
                    await _handle_timeout(
                        project_id, current_sub_phase, config.auto_advance_on_timeout,
                    )


async def _broadcast_warning(
    project_id: UUID,
    threshold_pct: int,
    sub_phase: str,
    used_seconds: int,
    budget_seconds: int,
) -> None:
    try:
        from app.events.bus import event_bus
        event = TimerWarningEvent(
            project_id=project_id,
            threshold_pct=threshold_pct,
            current_sub_phase=sub_phase,
            used_seconds=used_seconds,
            budget_seconds=budget_seconds,
        )
        await event_bus.publish(event)
        logger.info(
            "Timer warning project=%s sub_phase=%s pct=%d",
            project_id, sub_phase, threshold_pct,
        )
    except Exception:
        logger.warning("Timer warning broadcast failed", exc_info=True)


async def _handle_timeout(
    project_id: UUID,
    current_sub_phase: str,
    auto_advance: bool,
) -> None:
    try:
        from app.events.bus import event_bus
        timeout_event = TimerTimeoutEvent(
            project_id=project_id,
            current_sub_phase=current_sub_phase,
        )
        await event_bus.publish(timeout_event)
    except Exception:
        logger.warning("Timer timeout broadcast failed", exc_info=True)

    if not auto_advance:
        # 不強制推進 → 由 Stream D crew vote 接手或 Supervisor B11 主動問
        return

    # auto_advance=true：直接推進
    try:
        from app.agents.stage_advancement import advance_sub_phase
        from app.stages.sub_phases import get_next_sub_phase

        next_id = get_next_sub_phase(current_sub_phase)
        if next_id:
            result = await advance_sub_phase(
                project_id=project_id,
                agent_id="system_timer_auto_advance",
                from_sub_phase=current_sub_phase,
                to_sub_phase=next_id,
                skip_deliverable_check=False,  # 仍要過 deliverable
            )
            logger.info("Timer auto-advance result: %s", result)
    except Exception:
        logger.warning("Timer auto-advance failed", exc_info=True)
