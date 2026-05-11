"""Crew advance vote watcher — Spec 14 / Phase 18 Stream D.2.

每 10 秒：
  - 掃 active projects 的 timer used_pct
  - ≥90% 且 sub_phase 未變 → open_advance_vote
  - 也檢查既有 vote session 是否到期

由 main.py lifespan 啟動。
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.db.models.project import Project
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 10.0
_TRIGGER_THRESHOLD_PCT = 90.0
_SHUTDOWN = False


async def crew_vote_watcher_loop() -> None:
    global _SHUTDOWN
    _SHUTDOWN = False
    logger.info("crew_vote_watcher started")
    while not _SHUTDOWN:
        try:
            await _tick()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("crew_vote_watcher tick failed")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


async def stop_crew_vote_watcher() -> None:
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
            logger.debug("crew_vote check project=%s failed", p.id, exc_info=True)


async def _check_one(project_id: UUID, current_sub_phase: str | None) -> None:
    if not current_sub_phase:
        return

    # 1. Check existing session expiry
    try:
        from app.agents.crew_advance_vote import check_expiry, get_open_session
        result = await check_expiry(project_id)
        if result:
            logger.info(
                "crew_vote expired project=%s outcome=%s",
                project_id, result.outcome,
            )
            return  # Don't open new one same tick

        existing = await get_open_session(project_id)
        if existing:
            return  # Vote already in progress
    except Exception:
        logger.debug("crew_vote expiry check failed", exc_info=True)

    # 2. Check whether to trigger new vote
    try:
        from app.timer.service import TimerService
        used_pct = await TimerService.get_used_pct(project_id)
    except Exception:
        return

    if used_pct >= _TRIGGER_THRESHOLD_PCT:
        try:
            from app.agents.crew_advance_vote import open_advance_vote
            await open_advance_vote(
                project_id=project_id,
                current_sub_phase=current_sub_phase,
                triggered_by="system_timer_threshold",
                trigger_reason=f"timer reached {used_pct:.0f}%",
            )
        except Exception:
            logger.warning("open_advance_vote failed", exc_info=True)
