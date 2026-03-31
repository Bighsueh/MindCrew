"""MicroPhaseHistory CRUD repository."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.micro_phase_history import MicroPhaseHistory


class MicroPhaseHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        project_id: UUID,
        from_micro_phase: str,
        to_micro_phase: str,
        transition_type: str,
        triggered_by: str,
        reason: str | None = None,
        duration_seconds: int | None = None,
    ) -> MicroPhaseHistory:
        record = MicroPhaseHistory(
            project_id=project_id,
            from_micro_phase=from_micro_phase,
            to_micro_phase=to_micro_phase,
            transition_type=transition_type,
            triggered_by=triggered_by,
            reason=reason,
            duration_seconds=duration_seconds,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_by_project(self, project_id: UUID) -> list[MicroPhaseHistory]:
        result = await self.session.execute(
            select(MicroPhaseHistory)
            .where(MicroPhaseHistory.project_id == project_id)
            .order_by(MicroPhaseHistory.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_latest(self, project_id: UUID) -> MicroPhaseHistory | None:
        result = await self.session.execute(
            select(MicroPhaseHistory)
            .where(MicroPhaseHistory.project_id == project_id)
            .order_by(MicroPhaseHistory.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
