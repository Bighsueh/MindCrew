"""Stage history CRUD repository."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.stage_history import StageHistory


class StageHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        project_id: UUID,
        from_stage: str,
        to_stage: str,
        triggered_by: str,
        canvas_snapshot: dict | None = None,
        duration_seconds: int | None = None,
    ) -> StageHistory:
        record = StageHistory(
            project_id=project_id,
            from_stage=from_stage,
            to_stage=to_stage,
            triggered_by=triggered_by,
            canvas_snapshot=canvas_snapshot,
            duration_seconds=duration_seconds,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_by_project(self, project_id: UUID) -> list[StageHistory]:
        result = await self.session.execute(
            select(StageHistory)
            .where(StageHistory.project_id == project_id)
            .order_by(StageHistory.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_latest(self, project_id: UUID) -> StageHistory | None:
        result = await self.session.execute(
            select(StageHistory)
            .where(StageHistory.project_id == project_id)
            .order_by(StageHistory.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
