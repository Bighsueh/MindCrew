"""Teacher Dashboard API endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.bridge.canvas_ops import canvas_ops
from app.db.models.agent_decision_trace import AgentDecisionTrace
from app.db.models.message import Message
from app.db.models.project import Project
from app.db.models.seat import Seat
from app.db.models.stage_history import StageHistory
from app.db.models.user import User
from app.db.session import get_db_session
from app.teacher.schemas import (
    AgentTraceListResponse,
    AgentTraceResponse,
    LLMUsageSummary,
    ProjectRecordResponse,
    SeatSummary,
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
    msg_count_result = await session.execute(
        select(func.count(Message.id)).where(Message.project_id == project_id)
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
