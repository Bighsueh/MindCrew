"""Chat REST router：GET /api/projects/{id}/messages 支援 chat_id 過濾。

依 specs/13-personal-chat.md §5.1：
  - ``chat_id`` query 可為 ``"group"`` / ``"personal"`` / 完整 chat_id 字串。
  - 預設 ``None`` 視為 group（向下相容既有 client）。
  - 指向別人的 personal → 403；未知格式 → 400。
"""

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


def _classify_chat_id_error(message: str) -> int:
    """把 ``normalize_for_query`` 的 ValueError 訊息分類為 HTTP status。

    依 spec §8.1：
      - 「RBAC 違規」→ 403 Forbidden
      - 其他（未知格式 / 不屬於本專案 / 缺 owner）→ 400 Bad Request
    """
    if "RBAC 違規" in message:
        return status.HTTP_403_FORBIDDEN
    return status.HTTP_400_BAD_REQUEST


@router.get("/{project_id}/messages", response_model=MessagesListResponse)
async def get_project_messages(
    project_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = Query(default=None),
    chat_id: str | None = Query(
        default=None,
        description=(
            "選填。可為 'group'、'personal'、'{pid}:group' 或 "
            "'{pid}:personal:{your_user_id}'。預設為 group。"
        ),
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessagesListResponse:
    """Retrieve chat history for a project with cursor-based pagination.

    - ``limit``: number of messages to return (1–200, default 50)
    - ``before``: ISO 8601 timestamp; return only messages created before this time
    - ``chat_id``: 過濾通道；見 query 描述。

    RBAC 行為（spec §8.1）：
      - 群組 / 預設 → 回 group 訊息
      - 自己的 personal → 回自己的 personal 訊息
      - 別人的 personal → 403
      - 未知格式 → 400
    """
    service = ChatService(session)
    try:
        return await service.get_messages(
            project_id=project_id,
            limit=limit,
            before=before,
            chat_id=chat_id,
            current_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=_classify_chat_id_error(str(exc)),
            detail=str(exc),
        ) from exc
