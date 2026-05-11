"""Stability watcher — Spec 13 §3 / Phase 18 Step A10.

每 10 秒掃描所有 active project：當 sub_phase comm_mode 為 silent_rearrange
且連續無 canvas action ≥ stability_timeout_seconds → 自動 advance 到下一 sub_phase。

由 main.py startup 啟動為 asyncio background task。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.canvas.stability_detector import check_stability
from app.db.session import async_session_factory
from app.stages.sub_phases import SUB_PHASES, get_next_sub_phase, get_sub_phase

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 10.0
_SHUTDOWN: bool = False


async def stability_watcher_loop() -> None:
    """Background loop — runs forever. Stop by setting _SHUTDOWN=True."""
    global _SHUTDOWN
    _SHUTDOWN = False
    logger.info("stability_watcher started (poll interval=%ds)", _POLL_INTERVAL_SECONDS)
    while not _SHUTDOWN:
        try:
            await _tick()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("stability_watcher tick failed")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    logger.info("stability_watcher stopped")


async def stop_stability_watcher() -> None:
    global _SHUTDOWN
    _SHUTDOWN = True


async def _tick() -> None:
    """Single poll iteration: scan all active projects."""
    from sqlalchemy import select
    from app.db.models.project import Project

    async with async_session_factory() as session:
        rows = await session.execute(
            select(Project).where(Project.status == "active")
        )
        projects = rows.scalars().all()

    for project in projects:
        try:
            await _check_one_project(project.id, project.current_sub_phase)
        except Exception:
            logger.debug("stability check project=%s failed", project.id, exc_info=True)


async def _check_one_project(
    project_id: UUID,
    current_sub_phase: str | None,
) -> None:
    if not current_sub_phase:
        return
    sp = SUB_PHASES.get(current_sub_phase)
    if sp is None:
        return

    # Only auto-advance if current active comm_mode is silent_rearrange
    active_mode = sp.comm_modes[0] if sp.comm_modes else "discussion"
    if active_mode != "silent_rearrange":
        return

    stable = await check_stability(project_id, sp.stability_timeout_seconds)
    if not stable:
        return

    next_id = get_next_sub_phase(current_sub_phase)
    if next_id is None:
        return

    logger.info(
        "stability_watcher: project=%s %s stable for %ds → auto-advance to %s",
        project_id, current_sub_phase, sp.stability_timeout_seconds, next_id,
    )

    from app.agents.stage_advancement import advance_sub_phase
    # 自動推進視為「系統」操作，skip deliverable check（silent_rearrange 階段沒有寫入需求）
    result = await advance_sub_phase(
        project_id=project_id,
        agent_id="system_stability_watcher",
        from_sub_phase=current_sub_phase,
        to_sub_phase=next_id,
        skip_deliverable_check=True,
    )
    logger.info("stability auto-advance result: %s", result)
