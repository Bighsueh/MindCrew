"""DT 教練 endpoint router（Phase 20 重寫）。

POST /api/projects/{project_id}/dt-coach/ask

依 specs/13-personal-chat.md §5.2、§7、§8.2：
  - 必須帶 JWT；project 必須存在；user 必須是 seat 佔用者 OR creator。
  - 同步路徑：寫一筆 user message（chat_id=personal）→ publish event。
  - 非同步路徑：``asyncio.create_task`` 排程 Coach reply 背景任務，
    立即回 201 ack，避免 vLLM 慢時阻塞前端。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.chat.chat_id import make_personal_chat_id
from app.chat.repository import MessageRepository
from app.coach.schemas import (
    DTCoachAskRequest,
    DTCoachAskResponse,
    DTCoachUserMessageBrief,
)
from app.coach.service import dt_coach_service
from app.db.models.message import Message
from app.db.models.seat import Seat
from app.db.models.user import User
from app.db.session import get_db_session
from app.events.bus import event_bus
from app.events.types import ChatMessageEvent
from app.projects.repository import ProjectRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["dt-coach"])


async def _user_has_seat(
    session: AsyncSession, project_id: UUID, user_id: UUID
) -> bool:
    """檢查 user 是否為 project 的 seat 佔用者（與 ws/chat_ws.py 對齊）。"""
    result = await session.execute(
        select(Seat).where(
            Seat.project_id == project_id,
            Seat.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


@router.post(
    "/{project_id}/dt-coach/ask",
    response_model=DTCoachAskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ask_dt_coach(
    project_id: UUID,
    request: DTCoachAskRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DTCoachAskResponse:
    """向 DT 教練提問（非同步觸發）。

    Status codes:
        201: 已寫入 user message + 排程 Coach 回覆背景任務。
        401: JWT 缺失或無效（由 get_current_user 處理）。
        403: user 非 seat 佔用者也非 project creator（spec §8.2）。
        404: project_id 不存在。
        422: 請求 body 不符合 schema。

    spec §5.2：本 endpoint 不再回 503——LLM 失敗於背景處理（寫 system
    錯誤訊息 + WS 廣播）。
    """
    # 1) 確認 project 存在。
    repo_proj = ProjectRepository(session)
    project = await repo_proj.get_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # 2) RBAC：必須是 seat 佔用者 OR creator（spec §8.2）。
    is_creator = project.creator_id == current_user.id
    if not is_creator:
        has_seat = await _user_has_seat(session, project_id, current_user.id)
        if not has_seat:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a seat member or creator of this project",
            )

    # 3) 寫 user message（chat_id=personal:{current_user.id}）。
    personal_chat_id = make_personal_chat_id(project_id, current_user.id)
    user_message = Message(
        project_id=project_id,
        sender_type="human",
        sender_id=str(current_user.id),
        sender_name=current_user.display_name,
        content=request.content,
        stage=project.current_stage,
        chat_id=personal_chat_id,
    )
    repo_msg = MessageRepository(session)
    await repo_msg.create(user_message)
    # commit 由 get_db_session 結束時統一 commit（與 chat router 一致）。
    # 但這裡我們需要 created_at 確定值來回應，且要在 publish 前確保已落地，
    # 所以主動 commit 一次再 refresh。
    await session.commit()
    await session.refresh(user_message)

    created_at = user_message.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    created_at_iso = created_at.isoformat()

    # 4) Publish ChatMessageEvent（forwarder RBAC 過濾，只送回該 user 的 socket）。
    user_event = ChatMessageEvent(
        project_id=project_id,
        sender_id=str(current_user.id),
        sender_type="human",
        sender_name=current_user.display_name,
        content=request.content,
        chat_id=personal_chat_id,
        timestamp=created_at_iso,
    )
    try:
        await event_bus.publish(user_event)
    except Exception as exc:  # noqa: BLE001 — publish 失敗不該擋住 201 ack。
        logger.warning(
            "DT Coach user_message publish 失敗 project=%s user=%s err=%s",
            project_id,
            current_user.id,
            exc,
        )

    # 5) 排程 Coach reply 背景任務。
    #
    # 用 ``asyncio.create_task`` 而非 ``BackgroundTasks`` 的理由（spec §7.3）：
    #   - 背景任務不能用 request 的 session（已被 get_db_session 結尾 commit/close）；
    #     service 內部自建 session。
    #   - create_task 不綁定 request lifecycle，前端取消請求也不會中斷 Coach 回覆。
    asyncio.create_task(
        dt_coach_service.reply_to_personal_message(
            project_id=project_id,
            user_id=current_user.id,
            user_display_name=current_user.display_name,
            stage=request.stage,
            micro_phase=request.micro_phase,
            user_message_content=request.content,
        )
    )

    # 6) 立即回 201 ack。
    return DTCoachAskResponse(
        user_message=DTCoachUserMessageBrief(
            id=str(user_message.id),
            chat_id=personal_chat_id,
            content=user_message.content,
            created_at=created_at_iso,
        ),
        coach_reply_scheduled=True,
    )
