"""Timer watcher background loop — Spec 15 §4.2.

每 10 秒掃 active project：
  - 跨越 warning threshold (75/90/100%) → fire TimerWarningEvent
  - 100% + auto_advance → 呼叫 advance_sub_phase
  - 100% + !auto_advance → fire TimerTimeoutEvent（推進交由 progression watcher 兜底）
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.db.models.project import Project
from app.db.session import async_session_factory
from app.timer.calculator import get_phase_budget_seconds
from app.timer.events import TimerStateEvent, TimerTimeoutEvent, TimerWarningEvent
from app.timer.scaling import warmup_goal_for, warmup_soft_seconds_for
from app.timer.schemas import TimerConfig
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

    # ：每 tick 都廣播 state，讓所有訂閱者
    # （前端 TimerBadge、AI agent 觀察者）即時對齊 pause/resume 狀態。
    await _broadcast_state(
        project_id, current_sub_phase, used_secs, budget, used_pct,
        paused=False, config=config,
    )

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


async def _broadcast_state(
    project_id: UUID,
    sub_phase: str | None,
    used_seconds: int,
    budget_seconds: int,
    used_pct: float,
    paused: bool,
    config: TimerConfig | None = None,
) -> None:
    """每 tick 廣播一次 TimerStateEvent，讓前端與 AI 訂閱者即時對齊。"""
    try:
        from app.events.bus import event_bus
        event = TimerStateEvent(
            project_id=project_id,
            current_sub_phase=sub_phase,
            budget_seconds=budget_seconds,
            used_seconds=used_seconds,
            paused=paused,
            used_pct=used_pct,
            # Spec 16 v2.0 §4.5：本關上限/已用的明確化別名 + 暖場團隊目標。
            sub_phase_budget_seconds=budget_seconds,
            sub_phase_used_seconds=used_seconds,
            warmup_goal=warmup_goal_for(sub_phase, config),
            warmup_soft_seconds=warmup_soft_seconds_for(sub_phase, config),
        )
        await event_bus.publish(event)
    except Exception:
        logger.debug("Timer state broadcast failed", exc_info=True)


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
        # 不強制推進 → time-box 到的推進由 progression watcher 兜底與組長推進迴路負責
        # （spec 16 v2.0 §4 / spec 04-06 §5.8 v4.25），timer 模組不執行推進。
        return

    # auto_advance=true：直接推進。
    # ⚠️ Phase 42 D1d 註：此路徑直呼 advance_sub_phase、**繞過 execute_advance_target**，
    # 故不經 G01 真人硬閘——但它只在 time-box 100% timeout 觸發（時間到＝最終覆蓋，
    # 真人閘本就該豁免），語意正確。且所有現役 preset 皆 auto_advance_on_timeout=False
    # （見 timer/calculator.py），此路徑現況為 dead code，正常 time-box 推進由
    # progression watcher 兜底（skip_gate_check=True）負責。若未來啟用 auto_advance，
    # 應改走 execute_advance_target(skip_gate_check=True) 以正確處理 micro/macro 邊界。
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
