import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.constraints import (
    ConstraintSuggester,
    ConstraintSuggestionError,
)
from app.agents.personas.generator import (
    PersonaGenerationError,
    PersonaGenerator,
)
from app.auth.jwt import get_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.projects.schemas import (
    CanvasStateResponse,
    JoinRequest,
    JoinResponse,
    LinkTeacherRequest,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectTimerInitRequest,
    ProjectUpdateRequest,
    SeatResponse,
    StakeholderSuggestionPayload,
    SuggestConstraintsRequest,
    SuggestConstraintsResponse,
    SuggestStakeholdersRequest,
    SuggestStakeholdersResponse,
)
from app.projects.service import ProjectService
from app.seats.manager import seat_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Phase 27: Open Brief 三步驟 wizard draft endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/draft/suggest-constraints",
    response_model=SuggestConstraintsResponse,
)
async def suggest_constraints(
    request: SuggestConstraintsRequest,
    current_user: User = Depends(get_current_user),
) -> SuggestConstraintsResponse:
    """Phase 27 Step 1：根據 title+description 列建議的限制條件（chip 形式）。

    詳 `specs/17 §3.0.2` 與 `specs/17 §11` Open Brief 原則。
    """
    suggester = ConstraintSuggester()
    try:
        suggestions = await suggester.suggest(
            title=request.title,
            description=request.description,
            owning_user_id=current_user.id,
        )
    except ConstraintSuggestionError as exc:
        logger.warning("Constraint suggestion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 限制條件建議失敗，請稍後再試或自行填寫。",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return SuggestConstraintsResponse(**suggestions.as_dict())


@router.post(
    "/draft/suggest-stakeholders",
    response_model=SuggestStakeholdersResponse,
)
async def suggest_stakeholders(
    request: SuggestStakeholdersRequest,
    current_user: User = Depends(get_current_user),
) -> SuggestStakeholdersResponse:
    """Phase 27 Step 2：根據 title+description+constraints 列 6–10 位具體利害關係人。

    詳 `specs/17 §3.0.1`。
    """
    generator = PersonaGenerator()
    try:
        suggestions = await generator.suggest_stakeholders(
            title=request.title,
            description=request.description,
            constraints=request.constraints,
            owning_user_id=current_user.id,
            existing_names=request.existing_names,
        )
    except PersonaGenerationError as exc:
        logger.warning("Stakeholder suggestion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 利害關係人建議失敗，請稍後再試。",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    payloads = [
        StakeholderSuggestionPayload(
            id=s.id,
            name=s.name,
            role=s.role,
            relevance=s.relevance,
        )
        for s in suggestions
    ]
    return SuggestStakeholdersResponse(suggestions=payloads)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    result = await service.create_project(request, current_user)
    # Commit happens via get_db_session dependency; flush already ran.
    # Start agents after the session is flushed (seats exist in DB).
    await session.commit()
    try:
        await seat_manager.start_all_agents(result.id)
    except Exception as exc:
        logger.error("Failed to start agents for project %s: %s", result.id, exc)
    return result


@router.get("", response_model=list[ProjectListItem])
async def list_projects(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectListItem]:
    service = ProjectService(session)
    return await service.list_projects(current_user)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    return await service.get_project(project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    request: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    return await service.update_project(project_id, request, current_user)


@router.get("/{project_id}/seats", response_model=list[SeatResponse])
async def get_seats(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[SeatResponse]:
    service = ProjectService(session)
    return await service.get_seats(project_id)


@router.post("/{project_id}/join", response_model=JoinResponse)
async def join_project(
    project_id: UUID,
    request: JoinRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JoinResponse:
    service = ProjectService(session)
    return await service.join_project(project_id, request, current_user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = ProjectService(session)
    await service.delete_project(project_id, current_user)
    await session.commit()


# Phase 22: 學生 creator 將活動列管於某老師
@router.post("/{project_id}/link-teacher", response_model=ProjectResponse)
async def link_teacher(
    project_id: UUID,
    payload: LinkTeacherRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    result = await service.link_teacher(project_id, payload.signature_code, current_user)
    await session.commit()
    return result


@router.delete("/{project_id}/link-teacher", response_model=ProjectResponse)
async def unlink_teacher(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    service = ProjectService(session)
    result = await service.unlink_teacher(project_id, current_user)
    await session.commit()
    return result


@router.get("/{project_id}/canvas-state", response_model=CanvasStateResponse)
async def get_canvas_state(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CanvasStateResponse:
    service = ProjectService(session)
    return await service.get_canvas_state(project_id)


@router.post("/{project_id}/summary", response_model=ProjectSummaryResponse)
async def generate_summary(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectSummaryResponse:
    service = ProjectService(session)
    return await service.generate_summary(project_id, owning_user_id=current_user.id)


@router.post("/{project_id}/leave")
async def leave_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = ProjectService(session)
    return await service.leave_project(project_id, current_user)


# ---------------------------------------------------------------------------
# Spec 13 — 人類強制送出便條（force_publish）
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class HumanNoteRequest(BaseModel):
    text: str = Field(..., min_length=1)
    color: str = Field("yellow", pattern="^(yellow|pink|blue|green)$")
    x: float
    y: float
    sub_phase_id: str = Field(..., max_length=8)
    force_publish: bool = False


@router.post("/{project_id}/canvas/notes")
async def human_create_note(
    project_id: UUID,
    payload: HumanNoteRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Human-facing create_note endpoint with Spec 13 gates + force_publish support."""
    from app.canvas.tools_manipulation import tool_create_note

    result = await tool_create_note(
        project_id=project_id,
        text=payload.text,
        color=payload.color,
        position=f"absolute:{payload.x},{payload.y}",
        author_id=str(current_user.id),
        author_name=current_user.display_name,
        author_type="human",
        sub_phase_id=payload.sub_phase_id,
        force_publish=payload.force_publish,
    )
    return result


# ---------------------------------------------------------------------------
# Spec 14 N2: Crew Advance Vote endpoints
# ---------------------------------------------------------------------------


class AdvanceVoteCastRequest(BaseModel):
    choice: str = Field(..., pattern="^(approve|reject|abstain)$")


@router.get("/{project_id}/advance-vote")
async def get_advance_vote(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.agents.crew_advance_vote import get_open_session
    session = await get_open_session(project_id)
    return {"session": session}


@router.post("/{project_id}/advance-vote/cast")
async def cast_advance_vote(
    project_id: UUID,
    payload: AdvanceVoteCastRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.agents.crew_advance_vote import cast_vote
    result = await cast_vote(
        project_id=project_id,
        voter_id=str(current_user.id),
        voter_name=current_user.display_name,
        choice=payload.choice,  # type: ignore[arg-type]
    )
    if result is None:
        return {"success": False, "error": "no open vote"}
    return {
        "success": True,
        "outcome": result.outcome,
        "approve": result.approve_count,
        "reject": result.reject_count,
        "abstain": result.abstain_count,
    }


@router.post("/{project_id}/advance-vote/cancel")
async def cancel_advance_vote(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Teacher only — cancel an in-progress vote."""
    from app.agents.crew_advance_vote import cancel_vote
    ok = await cancel_vote(project_id, cancelled_by=str(current_user.id))
    return {"success": ok}


# ---------------------------------------------------------------------------
# Spec 15: Timer control endpoints
# ---------------------------------------------------------------------------


@router.get("/{project_id}/timer")
async def get_timer_state(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.timer.service import TimerService
    from app.timer.calculator import get_phase_budget_seconds

    state = await TimerService.get_state(project_id)
    config = await TimerService.get_config(project_id)
    if state is None or config is None:
        return {"available": False}

    budget = 0
    used_pct = 0.0
    used_seconds = 0
    if state.current_sub_phase:
        budget = get_phase_budget_seconds(config, state.current_sub_phase)
        used_seconds = TimerService._compute_used_seconds(state)
        if budget > 0:
            used_pct = used_seconds / budget * 100

    return {
        "available": True,
        "current_sub_phase": state.current_sub_phase,
        "budget_seconds": budget,
        "used_seconds": used_seconds,
        "used_pct": used_pct,
        "paused": state.is_paused(),
        "config": config.model_dump(),
        "state": state.model_dump(),
    }


@router.post("/{project_id}/timer/pause")
async def timer_pause(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.timer.service import TimerService
    new_state = await TimerService.pause(project_id)
    return {"success": new_state is not None, "state": new_state.model_dump() if new_state else None}


@router.post("/{project_id}/timer/resume")
async def timer_resume(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.timer.service import TimerService
    new_state = await TimerService.resume(project_id)
    return {"success": new_state is not None, "state": new_state.model_dump() if new_state else None}


class TimerExtendRequest(BaseModel):
    additional_minutes: int = Field(..., ge=1, le=60)


@router.post("/{project_id}/timer/extend")
async def timer_extend(
    project_id: UUID,
    payload: TimerExtendRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.timer.service import TimerService
    new_config = await TimerService.extend(project_id, payload.additional_minutes)
    return {"success": new_config is not None}


@router.post("/{project_id}/timer/init")
async def timer_init(
    project_id: UUID,
    payload: ProjectTimerInitRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """為尚未啟用 timer 的舊專案補上 timer_config + 啟動 sub_phase 1.1a。

    僅限 project creator；timer 已啟用回 409。config=None 走 DEFAULT_2HR_PRESET。
    """
    from fastapi import HTTPException
    from app.timer.service import TimerService

    project = await ProjectService(session).repo.get_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    if project.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有建立者可啟用計時器")
    if project.timer_config is not None:
        raise HTTPException(status_code=409, detail="計時器已啟用")

    await TimerService.initialize_project(project_id, config=payload.config)
    await TimerService.start_phase(project_id, "1.1a")
    return {"ok": True}
