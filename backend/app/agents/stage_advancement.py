"""Stage advancement logic: propose to humans or auto-advance.

Extracted from evaluator.py to keep files under 500 lines.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.agents.blackboard import BlackboardManager
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

_STAGE_ORDER = ["discover", "define", "develop", "deliver"]

_STAGE_NAMES = {
    "discover": "發現",
    "define": "定義",
    "develop": "發展",
    "deliver": "交付",
}

_PROPOSAL_TIMEOUT_SECONDS = 60.0


def get_next_stage(current: str) -> str | None:
    """Return the next stage in the Design Thinking sequence, or None."""
    try:
        idx = _STAGE_ORDER.index(current)
        if idx + 1 < len(_STAGE_ORDER):
            return _STAGE_ORDER[idx + 1]
    except ValueError:
        pass
    return None


async def propose_advance(
    stage: str,
    total_score: float,
    project_id: UUID,
    agent_id: str,
    proposal_event: asyncio.Event,
    get_proposal_agreed: callable,
    publish_supervisor_message: callable,
    threshold_ref: list[float],
    blackboard: BlackboardManager | None = None,
) -> str:
    """Propose stage advancement to humans via chat. Wait up to 60s."""
    current_name = _STAGE_NAMES.get(stage, stage)
    next_stage = get_next_stage(stage)
    if not next_stage:
        return "already_final_stage"

    next_name = _STAGE_NAMES.get(next_stage, next_stage)

    await publish_supervisor_message(
        f"我評估目前的 {current_name} 階段已經完成得相當充分（評分：{total_score:.0f} 分）。"
        f"大家覺得可以進入下一個 {next_name} 階段了嗎？"
    )

    proposal_event.clear()

    try:
        await asyncio.wait_for(
            proposal_event.wait(), timeout=_PROPOSAL_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.info("Stage advance proposal timed out — treating as agreed (silence = consent)")
        return await advance_stage(stage, project_id, agent_id, blackboard=blackboard)

    if get_proposal_agreed():
        return await advance_stage(stage, project_id, agent_id, blackboard=blackboard)
    else:
        threshold_ref[0] += 10.0
        logger.info(
            "Stage advance proposal rejected — threshold raised to %.1f",
            threshold_ref[0],
        )
        return "proposal_rejected"


async def advance_stage(
    current_stage: str,
    project_id: UUID,
    agent_id: str,
    blackboard: BlackboardManager | None = None,
) -> str:
    """Directly advance the project to the next stage."""
    next_stage = get_next_stage(current_stage)
    if not next_stage:
        logger.info("Already at final stage: %s", current_stage)
        return "already_final_stage"

    try:
        async with async_session_factory() as session:
            from sqlalchemy import update
            from app.db.models.project import Project
            from app.db.models.stage_history import StageHistory  # type: ignore[attr-defined]

            now = datetime.now(timezone.utc)

            await session.execute(
                update(StageHistory)
                .where(
                    StageHistory.project_id == project_id,
                    StageHistory.stage == current_stage,
                    StageHistory.ended_at.is_(None),
                )
                .values(ended_at=now)
            )

            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(current_stage=next_stage, updated_at=now)
            )

            sh = StageHistory(
                project_id=project_id,
                stage=next_stage,
                started_at=now,
            )
            session.add(sh)
            await session.commit()

        from app.events.types import StageChangedEvent
        from app.events.bus import event_bus

        event = StageChangedEvent(
            project_id=project_id,
            from_stage=current_stage,
            to=next_stage,
            triggered_by="ai_evaluator",
        )
        await event_bus.publish(event)

        if blackboard:
            await blackboard.clear_stage(next_stage)

        logger.info(
            "Project %s advanced: %s → %s",
            project_id,
            current_stage,
            next_stage,
        )
        return f"advanced_to_{next_stage}"
    except Exception as exc:
        logger.error("Failed to advance stage: %s", exc)
        return "advance_failed"
