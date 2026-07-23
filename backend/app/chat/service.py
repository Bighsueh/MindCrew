"""Chat service：包裝 repository 並處理分頁 + chat_id RBAC 解析。

`get_messages` 接受 router 傳入的 ``raw_chat_id`` 與 ``current_user_id``，
透過 ``app.chat.chat_id.normalize_for_query`` 解析後決定走 ``list_group``
還是 ``list_personal``。詳、§8.1。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import chat_id as chat_id_module
from app.chat.repository import MessageRepository
from app.chat.schemas import MessageResponse, MessagesListResponse


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MessageRepository(session)

    async def get_messages(
        self,
        project_id: UUID,
        *,
        limit: int = 50,
        before: datetime | None = None,
        chat_id: str | None = None,
        current_user_id: UUID | None = None,
    ) -> MessagesListResponse:
        """回傳指定 project 的訊息分頁。

        內部 fetch ``limit + 1`` 筆來判斷 ``has_more``，避免額外 COUNT。

        Args:
            project_id: 目標專案。
            limit: 1–200，由 router 把守。
            before: cursor。
            chat_id: 原始 query string 值（``None`` / ``"group"`` /
                ``"personal"`` / 完整字串）。預設視為 group。
            current_user_id: 當前 JWT 主體 user id；解析 ``personal`` 別名與
                RBAC 檢查需要。若 ``chat_id`` 為純 group 路徑可以省略，但
                為了 RBAC 一致性 router 應一律傳入。

        Returns:
            ``MessagesListResponse``，其中 ``MessageResponse.chat_id`` 帶 DB
            原值（可能為 ``None``）。

        Raises:
            ValueError: ``normalize_for_query`` 解析失敗時冒泡給 router，
                router 依錯誤訊息翻 400 / 403。
        """
        fetch_limit = min(limit, 200) + 1  # guard against large limits

        # RBAC：解析 chat_id 為 (kind, full_chat_id_or_None)。
        # 若 caller 未提供 current_user_id（例如純內部呼叫 group），
        # 給一個 zero UUID 走 group fallback（normalize 對 group 不會用到 user_id）。
        effective_user = current_user_id or UUID(int=0)
        kind, _full = chat_id_module.normalize_for_query(
            chat_id, project_id, effective_user
        )

        if kind == "personal":
            assert current_user_id is not None, (
                "personal chat_id 需要 current_user_id（router 應已強制提供）"
            )
            messages = await self.repo.list_personal(
                project_id,
                current_user_id,
                limit=fetch_limit,
                before=before,
            )
        else:
            messages = await self.repo.list_group(
                project_id,
                limit=fetch_limit,
                before=before,
            )

        has_more = len(messages) == fetch_limit
        if has_more:
            # Drop the extra sentinel row (oldest, first after reversal)
            messages = messages[1:]

        next_cursor: str | None = None
        if has_more and messages:
            next_cursor = messages[0].created_at.isoformat()

        return MessagesListResponse(
            messages=[MessageResponse.model_validate(m) for m in messages],
            has_more=has_more,
            next_cursor=next_cursor,
        )
