"""Teacher Dashboard API endpoints."""
from __future__ import annotations

import logging
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.bridge.canvas_ops import canvas_ops
from app.chat.message_filters import group_only_filter
from app.db.models.agent_decision_trace import AgentDecisionTrace
from app.db.models.message import Message
from app.db.models.project import Project
from app.db.models.seat import Seat
from app.db.models.stage_history import StageHistory
from app.db.models.stage_evaluation_log import StageEvaluationLog
from app.db.models.user import User
from app.db.session import get_db_session
from app.events.bus import event_bus
from app.events.types import ChatMessageEvent
from app.teacher.schemas import (
    AgentTraceListResponse,
    AgentTraceResponse,
    AIActivitySummary,
    AlertItem,
    EvaluationScoreSummary,
    LLMUsageSummary,
    ParticipationSummary,
    ProjectMonitorItem,
    ProjectOverviewResponse,
    ProjectRecordResponse,
    SeatSummary,
    SendHintRequest,
    SendHintResponse,
    StageDistribution,
    StageRecordEntry,
    TeacherProjectListItem,
)

router = APIRouter(tags=["teacher"])
logger = logging.getLogger(__name__)


def _require_teacher(current_user: User) -> User:
    """Raise 403 if the user is not a teacher."""
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers may access the dashboard",
        )
    return current_user


# ---------------------------------------------------------------------------
# GET /api/teacher/projects
# ---------------------------------------------------------------------------

@router.get("/api/teacher/projects", response_model=list[TeacherProjectListItem])
async def list_teacher_projects(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[TeacherProjectListItem]:
    _require_teacher(current_user)

    result = await session.execute(
        select(Project)
        .where(Project.creator_id == current_user.id)
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()

    items: list[TeacherProjectListItem] = []
    for p in projects:
        # Seat summary
        seat_result = await session.execute(
            select(Seat).where(Seat.project_id == p.id)
        )
        seats = seat_result.scalars().all()
        human_count = sum(1 for s in seats if s.occupant_type == "human")
        ai_count = sum(1 for s in seats if s.occupant_type == "ai")

        # Note count from in-memory canvas
        try:
            canvas_state = await canvas_ops.get_canvas_state(p.id)
            note_count = canvas_state.get("total_notes", 0)
        except Exception:
            note_count = 0

        items.append(
            TeacherProjectListItem(
                id=p.id,
                name=p.name,
                current_stage=p.current_stage,
                status=p.status,
                seat_summary=SeatSummary(human=human_count, ai=ai_count),
                note_count=note_count,
                last_activity=p.updated_at,
            )
        )
    return items


# ---------------------------------------------------------------------------
# GET /api/teacher/projects/{project_id}/record
# ---------------------------------------------------------------------------

@router.get(
    "/api/teacher/projects/{project_id}/record",
    response_model=ProjectRecordResponse,
)
async def get_project_record(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectRecordResponse:
    _require_teacher(current_user)

    # Project
    p_result = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = p_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the creator of this project",
        )

    # Stage history
    stage_history_result = await session.execute(
        select(StageHistory)
        .where(StageHistory.project_id == project_id)
        .order_by(StageHistory.created_at.asc())
    )
    stage_history_rows = stage_history_result.scalars().all()
    stages = [
        StageRecordEntry(
            stage=r.from_stage,
            duration_seconds=r.duration_seconds,
            canvas_snapshot=r.canvas_snapshot,
            started_at=r.created_at,
        )
        for r in stage_history_rows
    ]

    # Message count
    # spec §8.5：teacher dashboard 統計訊息數**只算 group**；
    # personal 訊息屬隱私邊界，不入 metric。
    msg_count_result = await session.execute(
        select(func.count(Message.id))
        .where(Message.project_id == project_id)
        .where(group_only_filter())
    )
    total_messages = msg_count_result.scalar() or 0

    # Note count
    try:
        canvas_state = await canvas_ops.get_canvas_state(project_id)
        total_notes = canvas_state.get("total_notes", 0)
    except Exception:
        total_notes = 0

    # LLM usage from decision traces
    llm_result = await session.execute(
        select(
            func.count(AgentDecisionTrace.id),
            func.coalesce(func.sum(AgentDecisionTrace.llm_tokens_in), 0),
            func.coalesce(func.sum(AgentDecisionTrace.llm_tokens_out), 0),
        ).where(AgentDecisionTrace.project_id == project_id)
    )
    llm_row = llm_result.one()
    total_calls = llm_row[0] or 0
    total_tokens = int(llm_row[1] or 0) + int(llm_row[2] or 0)
    # Cost estimate: rough approximation at $0.001 per 1k tokens
    total_cost_estimate = round(total_tokens / 1000 * 0.001, 6)
    llm_usage = LLMUsageSummary(
        total_tokens=total_tokens,
        total_calls=total_calls,
        total_cost_estimate=total_cost_estimate,
    )

    return ProjectRecordResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        current_stage=project.current_stage,
        ai_contribution=project.ai_contribution,
        status=project.status,
        created_at=project.created_at,
        stages=stages,
        total_messages=total_messages,
        total_notes=total_notes,
        llm_usage=llm_usage,
    )


# ---------------------------------------------------------------------------
# GET /api/teacher/projects/overview
# ---------------------------------------------------------------------------

@router.get("/api/teacher/projects/overview", response_model=ProjectOverviewResponse)
async def get_projects_overview(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectOverviewResponse:
    """Return full monitoring overview for all teacher's projects."""
    _require_teacher(current_user)

    result = await session.execute(
        select(Project)
        .where(Project.creator_id == current_user.id)
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()

    # Compute median stage duration across all active projects for alert thresholds
    stage_durations: dict[str, list[int]] = {}
    for p in projects:
        if p.status != "active" or p.current_stage == "completed":
            continue
        dur = _compute_stage_duration(p)
        stage_durations.setdefault(p.current_stage, []).append(dur)

    stage_medians: dict[str, float] = {}
    for stage, durations in stage_durations.items():
        sorted_d = sorted(durations)
        mid = len(sorted_d) // 2
        stage_medians[stage] = (
            sorted_d[mid]
            if len(sorted_d) % 2 == 1
            else (sorted_d[mid - 1] + sorted_d[mid]) / 2
        )

    items: list[ProjectMonitorItem] = []
    dist = StageDistribution()

    for p in projects:
        # Stage distribution count
        if hasattr(dist, p.current_stage):
            setattr(dist, p.current_stage, getattr(dist, p.current_stage) + 1)

        # Seat summary
        seat_result = await session.execute(
            select(Seat).where(Seat.project_id == p.id)
        )
        seats = seat_result.scalars().all()
        human_count = sum(1 for s in seats if s.occupant_type == "human")
        ai_count = sum(1 for s in seats if s.occupant_type == "ai")

        # Note count
        try:
            canvas_state = await canvas_ops.get_canvas_state(p.id)
            note_count = canvas_state.get("total_notes", 0)
        except Exception:
            note_count = 0

        # Stage duration
        stage_duration = _compute_stage_duration(p)

        # Stage started_at: last transition's created_at, or project created_at
        stage_started_result = await session.execute(
            select(StageHistory.created_at)
            .where(StageHistory.project_id == p.id)
            .order_by(StageHistory.created_at.desc())
            .limit(1)
        )
        last_transition = stage_started_result.scalar_one_or_none()
        stage_started_at = last_transition if last_transition else p.created_at

        # Evaluation score
        eval_result = await session.execute(
            select(StageEvaluationLog)
            .where(
                StageEvaluationLog.project_id == p.id,
                StageEvaluationLog.stage == p.current_stage,
            )
            .order_by(StageEvaluationLog.created_at.desc())
            .limit(5)
        )
        evals = eval_result.scalars().all()
        evaluation_score = _build_evaluation_summary(evals)

        # Participation
        participation = await _build_participation(session, p.id, seats)

        # AI activity
        ai_activity = await _build_ai_activity(session, p.id)

        # Alerts
        alerts = _compute_alerts(
            p, stage_duration, stage_medians, evaluation_score, participation, ai_activity
        )

        items.append(
            ProjectMonitorItem(
                id=p.id,
                name=p.name,
                current_stage=p.current_stage,
                status=p.status,
                seat_summary=SeatSummary(human=human_count, ai=ai_count),
                note_count=note_count,
                last_activity=p.updated_at,
                created_at=p.created_at,
                ai_contribution=p.ai_contribution,
                stage_duration_seconds=stage_duration,
                stage_started_at=stage_started_at,
                evaluation_score=evaluation_score,
                participation=participation,
                ai_activity=ai_activity,
                alerts=alerts,
            )
        )

    return ProjectOverviewResponse(projects=items, stage_distribution=dist)


# ---------------------------------------------------------------------------
# POST /api/teacher/projects/{project_id}/send-hint
# ---------------------------------------------------------------------------

@router.post(
    "/api/teacher/projects/{project_id}/send-hint",
    response_model=SendHintResponse,
)
async def send_hint(
    project_id: UUID,
    body: SendHintRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SendHintResponse:
    """Teacher sends a hint message to a project's chatroom."""
    _require_teacher(current_user)

    # Verify project exists and belongs to teacher
    p_result = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = p_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the creator of this project",
        )

    now = datetime.now(timezone.utc)
    msg_id = uuid_mod.uuid4()

    # Save message to DB
    msg = Message(
        id=msg_id,
        project_id=project_id,
        sender_type="system",
        sender_id=str(current_user.id),
        sender_name=f"{current_user.display_name} 老師",
        content=body.content,
        stage=project.current_stage,
        created_at=now,
    )
    session.add(msg)
    await session.flush()

    # Publish via event bus so WebSocket clients see it in real time
    event = ChatMessageEvent(
        project_id=project_id,
        sender_id=str(current_user.id),
        sender_type="system",
        sender_name=f"{current_user.display_name} 老師",
        content=body.content,
        timestamp=now.isoformat(),
        id=str(msg_id),
    )
    await event_bus.publish(event)

    return SendHintResponse(message_id=msg_id, sent_at=now)


# ---------------------------------------------------------------------------
# Monitoring helper functions
# ---------------------------------------------------------------------------

def _compute_stage_duration(project: Project) -> int:
    """Compute seconds the project has been in its current stage."""
    now = datetime.now(timezone.utc)
    updated = project.updated_at
    if updated and updated.tzinfo is None:
        from datetime import timezone as tz
        updated = updated.replace(tzinfo=tz.utc)
    return int((now - updated).total_seconds()) if updated else 0


def _build_evaluation_summary(
    evals: list[StageEvaluationLog],
) -> EvaluationScoreSummary:
    """Build evaluation score summary from recent evaluations."""
    if not evals:
        return EvaluationScoreSummary(
            latest_total=None,
            threshold=None,
            consecutive_passes=0,
            trend="stagnant",
        )

    latest = evals[0]
    trend = "stagnant"
    if len(evals) >= 3:
        scores = [e.total_score for e in evals[:3] if e.total_score is not None]
        if len(scores) >= 3:
            if scores[0] > scores[1] > scores[2]:
                trend = "declining"  # newest > older = improving (but list is newest-first)
            # Actually: evals[0] is newest. If newest > second > third, it's improving
            if scores[0] > scores[2]:
                trend = "improving"
            elif scores[0] < scores[2]:
                trend = "declining"

    return EvaluationScoreSummary(
        latest_total=latest.total_score,
        threshold=latest.threshold,
        consecutive_passes=latest.consecutive_pass_count,
        trend=trend,
    )


async def _build_participation(
    session: AsyncSession, project_id: UUID, seats: list[Seat],
) -> ParticipationSummary:
    """Build participation summary from message counts."""
    # spec §8.5：以下三個統計皆只算 group 訊息，personal 不入 metric。
    # Human message count
    human_msg_result = await session.execute(
        select(func.count(Message.id))
        .where(
            Message.project_id == project_id,
            Message.sender_type == "human",
        )
        .where(group_only_filter())
    )
    human_messages = human_msg_result.scalar() or 0

    # AI message count
    ai_msg_result = await session.execute(
        select(func.count(Message.id))
        .where(
            Message.project_id == project_id,
            Message.sender_type == "ai",
        )
        .where(group_only_filter())
    )
    ai_messages = ai_msg_result.scalar() or 0

    # Active members: humans who sent at least one message
    # 注意：personal 也是 human 發的，但若以 personal 訊息算「有發言」會違反 §8.5；
    # 故此處同樣只看 group 發言。
    active_result = await session.execute(
        select(func.count(func.distinct(Message.sender_id)))
        .where(
            Message.project_id == project_id,
            Message.sender_type == "human",
        )
        .where(group_only_filter())
    )
    active_members = active_result.scalar() or 0

    total_members = sum(1 for s in seats if s.occupant_type == "human")

    return ParticipationSummary(
        human_messages=human_messages,
        ai_messages=ai_messages,
        active_members=active_members,
        total_members=total_members,
    )


async def _build_ai_activity(
    session: AsyncSession, project_id: UUID,
) -> AIActivitySummary:
    """Build AI activity summary from agent decision traces."""
    # Total interventions (action_type is not null and not 'no_action')
    total_result = await session.execute(
        select(func.count(AgentDecisionTrace.id)).where(
            AgentDecisionTrace.project_id == project_id,
            AgentDecisionTrace.assess_result == "intervene",
        )
    )
    total_interventions = total_result.scalar() or 0

    # Recent interventions (last 10 minutes)
    ten_min_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    recent_result = await session.execute(
        select(func.count(AgentDecisionTrace.id)).where(
            AgentDecisionTrace.project_id == project_id,
            AgentDecisionTrace.assess_result == "intervene",
            AgentDecisionTrace.created_at >= ten_min_ago,
        )
    )
    recent_interventions = recent_result.scalar() or 0

    # Action type distribution
    dist_result = await session.execute(
        select(
            AgentDecisionTrace.action_type,
            func.count(AgentDecisionTrace.id),
        )
        .where(
            AgentDecisionTrace.project_id == project_id,
            AgentDecisionTrace.action_type.isnot(None),
        )
        .group_by(AgentDecisionTrace.action_type)
    )
    action_distribution = {row[0]: row[1] for row in dist_result.all()}

    return AIActivitySummary(
        total_interventions=total_interventions,
        recent_interventions=recent_interventions,
        action_distribution=action_distribution,
    )


def _compute_alerts(
    project: Project,
    stage_duration: int,
    stage_medians: dict[str, float],
    evaluation: EvaluationScoreSummary,
    participation: ParticipationSummary,
    ai_activity: AIActivitySummary,
) -> list[AlertItem]:
    """Compute alert items based on monitoring rules."""
    alerts: list[AlertItem] = []

    if project.current_stage == "completed":
        return alerts

    median = stage_medians.get(project.current_stage, 0)

    # Stage stagnation - red
    if (
        median > 0
        and stage_duration > median * 2
        and evaluation.consecutive_passes == 0
        and evaluation.latest_total is not None
        and evaluation.threshold is not None
        and evaluation.latest_total < evaluation.threshold
    ):
        alerts.append(AlertItem(
            level="error",
            type="stage_stagnation",
            message=f"已在 {project.current_stage.capitalize()} 階段停留過久（{stage_duration // 60} 分鐘），且評估分數持續未達標",
        ))
    # Stage stagnation - yellow
    elif median > 0 and stage_duration > median * 1.5:
        alerts.append(AlertItem(
            level="warning",
            type="stage_stagnation",
            message=f"在 {project.current_stage.capitalize()} 階段已停留 {stage_duration // 60} 分鐘，超過全班中位數",
        ))

    # Low participation
    if participation.total_members > 0 and participation.active_members < participation.total_members:
        silent = participation.total_members - participation.active_members
        alerts.append(AlertItem(
            level="warning",
            type="low_participation",
            message=f"有 {silent} 位成員尚未發言",
        ))

    # AI dominant
    if (
        participation.human_messages > 0
        and participation.ai_messages > participation.human_messages * 3
    ):
        alerts.append(AlertItem(
            level="info",
            type="ai_dominant",
            message="AI 發言數明顯高於人類發言數，可能需要關注",
        ))

    return alerts


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/agent-traces
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/agent-traces",
    response_model=AgentTraceListResponse,
)
async def list_agent_traces(
    project_id: UUID,
    agent_id: str | None = Query(default=None, description="Filter by agent_id"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, description="ISO datetime cursor for pagination"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentTraceListResponse:
    _require_teacher(current_user)

    query = select(AgentDecisionTrace).where(
        AgentDecisionTrace.project_id == project_id
    )

    if agent_id:
        query = query.where(AgentDecisionTrace.agent_id == agent_id)

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.where(AgentDecisionTrace.created_at < cursor_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor format"
            )

    query = query.order_by(AgentDecisionTrace.created_at.desc()).limit(limit + 1)
    result = await session.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor: str | None = None
    if has_more and items:
        next_cursor = items[-1].created_at.isoformat()

    return AgentTraceListResponse(
        traces=[_trace_to_response(t) for t in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/agent-traces/{trace_id}
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/agent-traces/{trace_id}",
    response_model=AgentTraceResponse,
)
async def get_agent_trace(
    project_id: UUID,
    trace_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentTraceResponse:
    _require_teacher(current_user)

    result = await session.execute(
        select(AgentDecisionTrace).where(
            AgentDecisionTrace.id == trace_id,
            AgentDecisionTrace.project_id == project_id,
        )
    )
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")

    return _trace_to_response(trace)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trace_to_response(t: AgentDecisionTrace) -> AgentTraceResponse:
    return AgentTraceResponse(
        id=t.id,
        project_id=t.project_id,
        agent_id=t.agent_id,
        stage=t.stage,
        assess_result=t.assess_result,
        assess_rule=t.assess_rule,
        assess_details=t.assess_details,
        prompt_text=t.prompt_text,
        llm_response=t.llm_response,
        llm_model=t.llm_model,
        llm_tokens_in=t.llm_tokens_in,
        llm_tokens_out=t.llm_tokens_out,
        llm_latency_ms=t.llm_latency_ms,
        action_type=t.action_type,
        action_details=t.action_details,
        action_result=t.action_result,
        created_at=t.created_at,
    )
