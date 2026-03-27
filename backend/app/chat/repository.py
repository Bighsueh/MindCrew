from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_messages(
        self,
        project_id: UUID,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[Message]:
        """
        Cursor-based pagination.

        Returns up to `limit` messages for the project, ordered by
        created_at DESC (newest first), optionally filtered to those
        created before the `before` timestamp cursor.
        """
        query = (
            select(Message)
            .where(Message.project_id == project_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        if before is not None:
            query = query.where(Message.created_at < before)

        result = await self.session.execute(query)
        # Return in ascending order so the client sees oldest→newest
        rows = list(result.scalars().all())
        return list(reversed(rows))

    async def create(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.flush()
        return message
