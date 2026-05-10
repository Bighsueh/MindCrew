import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.projects.schemas import (
    CanvasStateResponse,
    JoinRequest,
    JoinResponse,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
    SeatResponse,
)
from app.projects.service import ProjectService
from app.seats.manager import seat_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


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
    return await service.generate_summary(project_id)


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
