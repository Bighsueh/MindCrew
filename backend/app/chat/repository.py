"""Message repository — chat history 的唯一 SQL 入口。

「強制收斂點」：
  - 任何 message 表的讀取**必須**走本檔案的 ``list_group`` /
    ``list_personal`` / ``list_for_agents``，禁止 inline ``select(Message)``。
  - ``get_messages`` 保留為 ``list_group`` 的向下相容別名。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.chat_id import GROUP_SUFFIX, make_personal_chat_id
from app.db.models.message import Message


class MessageRepository:
    """Message DB 存取層。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 公開查詢方法（依 spec §4.4 收斂）
    # ------------------------------------------------------------------

    async def list_group(
        self,
        project_id: UUID,
        *,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[Message]:
        """讀群組訊息。

        Filter：``chat_id IS NULL OR chat_id LIKE '%:group'``，
        對應 spec §4.3.3 的「群組 / 向下相容」語意。

        Args:
            project_id: 目標專案。
            limit: 最多回傳幾筆。
            before: cursor，僅回傳 ``created_at < before`` 的訊息。

        Returns:
            訊息列表，依 ``created_at`` 由舊至新排序（給前端直接顯示）。
        """
        query = (
            select(Message)
            .where(Message.project_id == project_id)
            .where(
                or_(
                    Message.chat_id.is_(None),
                    Message.chat_id.like(f"%{GROUP_SUFFIX}"),
                )
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        if before is not None:
            query = query.where(Message.created_at < before)

        result = await self.session.execute(query)
        rows = list(result.scalars().all())
        return list(reversed(rows))

    async def list_personal(
        self,
        project_id: UUID,
        user_id: UUID,
        *,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[Message]:
        """讀某 user 的個人訊息。

        Filter：``chat_id == '{project_id}:personal:{user_id}'``。
        chat_id 字串透過 ``make_personal_chat_id`` 集中組裝，避免 typo。

        Args:
            project_id: 目標專案。
            user_id: 個人聊天屬主。
            limit: 最多回傳幾筆。
            before: cursor。

        Returns:
            訊息列表，依 ``created_at`` 由舊至新排序。
        """
        chat_id = make_personal_chat_id(project_id, user_id)
        query = (
            select(Message)
            .where(Message.project_id == project_id)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        if before is not None:
            query = query.where(Message.created_at < before)

        result = await self.session.execute(query)
        rows = list(result.scalars().all())
        return list(reversed(rows))

    async def list_for_agents(
        self,
        project_id: UUID,
        *,
        limit: int = 50,
    ) -> list[Message]:
        """專供 agent context_buffer 用：**僅 group**。

        強制收斂點（spec §4.4、§9.1）——下游 agent 邏輯不直接 ``select(Message)``，
        一律走這個 method，確保任何 LLM prompt 都不會看到 personal 訊息。

        語意等同 ``list_group``，但獨立命名以便未來在 CI grep 規則中
        允許 agent 路徑只 import 這個 method。
        """
        return await self.list_group(project_id, limit=limit)

    # ------------------------------------------------------------------
    # 向下相容
    # ------------------------------------------------------------------

    async def get_messages(
        self,
        project_id: UUID,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[Message]:
        """**Deprecated**：保留為 ``list_group`` 的別名以維持既有 caller 行為。

        Phase 20 起新程式應改用 ``list_group`` / ``list_personal`` /
        ``list_for_agents``。本方法行為等同 ``list_group``（只回 group 訊息）。
        """
        return await self.list_group(
            project_id,
            limit=limit,
            before=before,
        )

    # ------------------------------------------------------------------
    # 寫入
    # ------------------------------------------------------------------

    async def create(self, message: Message) -> Message:
        """寫入訊息（chat_id 由 caller 設定）。"""
        self.session.add(message)
        await self.session.flush()
        return message
