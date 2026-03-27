from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.repository import MessageRepository
from app.chat.schemas import MessageResponse, MessagesListResponse


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MessageRepository(session)

    async def get_messages(
        self,
        project_id: UUID,
        limit: int = 50,
        before: datetime | None = None,
    ) -> MessagesListResponse:
        """
        Return paginated message history for a project.

        Fetches `limit + 1` rows internally to determine whether a next
        page exists without an extra COUNT query.
        """
        fetch_limit = min(limit, 200) + 1  # guard against large limits
        messages = await self.repo.get_messages(
            project_id=project_id,
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
