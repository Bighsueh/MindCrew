"""Progress summary builders for seat transitions.

Extracted from manager.py to keep each file under 500 lines.
Provides build_regular_progress_summary and build_supervisor_progress_summary.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select, desc

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


def _summarize_topic(messages: list) -> str:
    """Extract a brief topic hint from the most recent chat messages."""
    if not messages:
        return "尚無討論記錄"
    contents = [
        m.content for m in messages[-5:] if hasattr(m, "content") and m.content
    ]
    if not contents:
        return "尚無討論記錄"
    last = contents[-1]
    return last[:30] + "…" if len(last) > 30 else last


async def build_regular_progress_summary(project_id: UUID) -> str:
    """Build a concise progress summary for regular (non-supervisor) seats (spec §7.2).

    Format: 目前在 {stage} 階段，白板上有 {note_count} 張便條紙，主要在討論 {topic}
    """
    try:
        from app.bridge.canvas_ops import canvas_ops
        from app.chat.message_filters import group_only_filter
        from app.db.models.message import Message
        from app.db.models.project import Project

        async with async_session_factory() as session:
            p_result = await session.execute(
                select(Project).where(Project.id == project_id)
            )
            project = p_result.scalar_one_or_none()
            if project is None:
                return "（無法取得專案資訊）"
            stage = project.current_stage

            # spec §9.1：Supervisor handoff / progress summary 是 agent 看的內容，
            # 不能混入任何 personal chat 訊息，因此一律過濾為 group only。
            msg_result = await session.execute(
                select(Message)
                .where(Message.project_id == project_id)
                .where(group_only_filter())
                .order_by(desc(Message.created_at))
                .limit(10)
            )
            recent_msgs = list(reversed(msg_result.scalars().all()))

        canvas = await canvas_ops.get_canvas_state(project_id)
        note_count = canvas.get("total_notes", 0)
        topic = _summarize_topic(recent_msgs)

        return (
            f"目前在 {stage} 階段，白板上有 {note_count} 張便條紙，主要在討論 {topic}"
        )
    except Exception as exc:
        logger.warning("Failed to build regular progress summary: %s", exc)
        return "（進度摘要暫時無法載入）"


async def build_supervisor_progress_summary(project_id: UUID) -> str:
    """Build a detailed progress summary for Supervisor seats (spec §7.3).

    Includes stage, duration, canvas stats, evaluation scores, and topic.
    """
    try:
        from app.bridge.canvas_ops import canvas_ops
        from app.chat.message_filters import group_only_filter
        from app.db.models.message import Message
        from app.db.models.project import Project
        from app.db.models.stage_evaluation_log import StageEvaluationLog
        from datetime import datetime, timezone

        async with async_session_factory() as session:
            p_result = await session.execute(
                select(Project).where(Project.id == project_id)
            )
            project = p_result.scalar_one_or_none()
            if project is None:
                return "（無法取得專案資訊）"
            stage = project.current_stage

            # Stage duration
            duration_minutes = 0
            try:
                from app.db.models.stage_history import StageHistory  # type: ignore[attr-defined]
                history_result = await session.execute(
                    select(StageHistory)
                    .where(
                        StageHistory.project_id == project_id,
                        StageHistory.stage == stage,
                        StageHistory.ended_at.is_(None),
                    )
                    .order_by(desc(StageHistory.started_at))
                    .limit(1)
                )
                sh = history_result.scalar_one_or_none()
                if sh and sh.started_at:
                    started = sh.started_at
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    duration_minutes = int(
                        (datetime.now(timezone.utc) - started).total_seconds() / 60
                    )
            except Exception:
                pass

            # Latest evaluation scores
            eval_result = await session.execute(
                select(StageEvaluationLog)
                .where(StageEvaluationLog.project_id == project_id)
                .order_by(desc(StageEvaluationLog.created_at))
                .limit(1)
            )
            latest_eval = eval_result.scalar_one_or_none()
            quant_score = (
                f"{latest_eval.quantitative_score:.0f}"
                if latest_eval and latest_eval.quantitative_score is not None
                else "N/A"
            )
            qual_score = (
                f"{latest_eval.qualitative_score:.0f}"
                if latest_eval and latest_eval.qualitative_score is not None
                else "N/A"
            )

            # Recent chat for topic
            # spec §9.1：同上，Supervisor 看到的進度摘要不得包含 personal。
            msg_result = await session.execute(
                select(Message)
                .where(Message.project_id == project_id)
                .where(group_only_filter())
                .order_by(desc(Message.created_at))
                .limit(10)
            )
            recent_msgs = list(reversed(msg_result.scalars().all()))

        canvas = await canvas_ops.get_canvas_state(project_id)
        total_notes = canvas.get("total_notes", 0)
        groups = canvas.get("groups", [])
        ungrouped = canvas.get("ungrouped", [])
        group_count = len(groups)
        ungrouped_count = len(ungrouped)
        topic_summary = _summarize_topic(recent_msgs)

        return (
            f"歡迎接手 Supervisor！這是目前的進度摘要：\n"
            f"- 目前在 {stage} 階段，已進行 {duration_minutes} 分鐘\n"
            f"- 白板上有 {total_notes} 張便條紙，已分成 {group_count} 個群組\n"
            f"- 還有 {ungrouped_count} 張未分群的便條紙\n"
            f"- 團隊正在討論的主題：{topic_summary}\n"
            f"- 階段評估分數：量化 {quant_score}、質性 {qual_score}\n"
            f"祝你順利引導！"
        )
    except Exception as exc:
        logger.warning("Failed to build supervisor progress summary: %s", exc)
        return "（進度摘要暫時無法載入）"
