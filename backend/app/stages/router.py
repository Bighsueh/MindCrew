"""DT Flow stage endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.stages.schemas import AdvanceStageRequest, AdvanceStageResponse, StageHistoryResponse, StageResponse
from app.stages.service import StageService

router = APIRouter(prefix="/api/projects", tags=["stages"])


@router.get("/{project_id}/stage", response_model=StageResponse)
async def get_stage(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StageResponse:
    service = StageService(session)
    return await service.get_stage(project_id)


@router.post(
    "/{project_id}/advance-stage",
    response_model=AdvanceStageResponse,
    status_code=status.HTTP_200_OK,
)
async def advance_stage(
    project_id: UUID,
    request: AdvanceStageRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AdvanceStageResponse:
    service = StageService(session)
    return await service.advance_stage(
        project_id=project_id,
        triggered_by=str(current_user.id),
        from_stage=request.from_stage,
        to_stage=request.to_stage,
        reason=request.reason,
        supervisor_user_id=current_user.id,
    )


@router.get("/{project_id}/history", response_model=list[StageHistoryResponse])
async def get_stage_history(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[StageHistoryResponse]:
    service = StageService(session)
    return await service.list_history(project_id)
