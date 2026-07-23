from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MessageResponse(BaseModel):
    id: UUID
    project_id: UUID
    sender_type: str
    sender_id: str
    sender_name: str
    content: str
    stage: str
    created_at: datetime
    # chat_id：群組訊息可能為 None（向下相容既有 row）或 ``{pid}:group``；
    # 個人訊息為 ``{pid}:personal:{user_id}``。詳。
    chat_id: str | None = None

    model_config = {"from_attributes": True}


class MessagesListResponse(BaseModel):
    messages: list[MessageResponse]
    has_more: bool
    next_cursor: str | None  # ISO timestamp of the oldest message returned
