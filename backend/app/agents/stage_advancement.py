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

            # 同步更新 current_micro_phase（修復 macro boundary crossing bug — Phase 13）
            from app.stages.micro_phases import get_first_micro_phase_for_stage
            first_micro = get_first_micro_phase_for_stage(next_stage)
            update_values: dict = {"current_stage": next_stage, "updated_at": now}
            if first_micro:
                update_values["current_micro_phase"] = first_micro

            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(**update_values)
            )

            sh = StageHistory(
                project_id=project_id,
                from_stage=current_stage,
                to_stage=next_stage,
                triggered_by="ai_evaluator",
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


async def advance_micro_phase(
    project_id: UUID,
    agent_id: str,
    from_phase: str,
    to_phase: str,
) -> str:
    """Advance micro phase via direct DB update (within same macro stage).

    Returns the new micro phase ID prefixed with 'micro_advanced_to_'.
    """
    try:
        async with async_session_factory() as session:
            from sqlalchemy import update
            from app.db.models.project import Project
            from app.db.models.micro_phase_history import MicroPhaseHistory  # type: ignore[attr-defined]

            now = datetime.now(timezone.utc)

            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(current_micro_phase=to_phase, updated_at=now)
            )

            mp_hist = MicroPhaseHistory(
                project_id=project_id,
                from_micro_phase=from_phase,
                to_micro_phase=to_phase,
                transition_type="advance",
                triggered_by=agent_id,
            )
            session.add(mp_hist)
            await session.commit()

            # Publish event INSIDE the try block right after commit
            # to prevent split-transaction (DB committed but event not sent)
            from app.events.types import MicroPhaseChangedEvent
            from app.events.bus import event_bus

            event = MicroPhaseChangedEvent(
                project_id=project_id,
                from_phase=from_phase,
                to_phase=to_phase,
                transition_type="advance",
                triggered_by=agent_id,
            )
            await event_bus.publish(event)

        # Announce transition via chat (best-effort, outside DB session)
        try:
            from app.stages.micro_phases import get_micro_phase
            from app.events.types import ChatMessageEvent
            from app.events.bus import event_bus as _eb
            from app.chinese.converter import chinese_converter

            try:
                mp = get_micro_phase(to_phase)
                phase_name = mp.name_zh
            except KeyError:
                phase_name = to_phase

            announcement = chinese_converter.convert(
                f"我們已完成上一步驟，現在進入「{phase_name}」（{to_phase}）階段。"
            )
            chat_event = ChatMessageEvent(
                project_id=project_id,
                sender_id=agent_id,
                sender_type="ai",
                sender_name="Supervisor",
                content=announcement,
            )
            await _eb.publish(chat_event)
        except Exception as exc:
            logger.warning("Failed to announce micro phase transition: %s", exc)

        # Auto-tidy on convergence phase transitions (Phase 14: uses tidy_area)
        _AUTO_TIDY_PHASES: set[str] = {"1.3", "3.2"}
        if to_phase in _AUTO_TIDY_PHASES:
            try:
                from app.canvas.tools_manipulation import tool_tidy_area
                await tool_tidy_area(project_id, scope="all", strategy="align_grid")
                logger.info("Auto-tidy applied for phase %s", to_phase)
            except Exception as exc:
                logger.warning("Auto-tidy failed for phase %s: %s", to_phase, exc)

        logger.info(
            "Project %s micro phase advanced: %s → %s",
            project_id,
            from_phase,
            to_phase,
        )
        return f"micro_advanced_to_{to_phase}"
    except Exception as exc:
        logger.error("Failed to advance micro phase: %s", exc)
        return "micro_advance_failed"
