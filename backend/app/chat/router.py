from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.chat.schemas import MessagesListResponse
from app.chat.service import ChatService
from app.db.models.user import User
from app.db.session import get_db_session

router = APIRouter(prefix="/api/projects", tags=["chat"])


@router.get("/{project_id}/messages", response_model=MessagesListResponse)
async def get_project_messages(
    project_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessagesListResponse:
    """
    Retrieve chat history for a project with cursor-based pagination.

    - **limit**: number of messages to return (1–200, default 50)
    - **before**: ISO 8601 timestamp; return only messages created before this time
    """
    service = ChatService(session)
    return await service.get_messages(
        project_id=project_id,
        limit=limit,
        before=before,
    )
