"""Stage advance logic — DT Flow service layer."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bridge.canvas_ops import canvas_ops
from app.db.models.project import Project
from app.db.models.seat import Seat
from app.db.models.stage_history import StageHistory
from app.events.bus import event_bus
from app.events.types import StageChangedEvent
from app.stages.repository import StageHistoryRepository
from app.stages.schemas import AdvanceStageResponse, StageHistoryResponse, StageResponse

logger = logging.getLogger(__name__)

# Valid DT stage transitions
_VALID_TRANSITIONS: dict[str, str] = {
    "discover": "define",
    "define": "develop",
    "develop": "deliver",
    "deliver": "completed",
}


class StageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = StageHistoryRepository(session)

    async def get_stage(self, project_id: UUID) -> StageResponse:
        project = await self._get_project_or_404(project_id)
        return StageResponse(
            project_id=project.id,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
        )

    async def advance_stage(
        self,
        project_id: UUID,
        triggered_by: str,
        from_stage: str,
        to_stage: str,
        reason: str | None,
        supervisor_user_id: UUID,
    ) -> AdvanceStageResponse:
        """Advance project stage; only the supervisor-seat occupant may call this."""
        project = await self._get_project_or_404(project_id)

        # Validate supervisor permission
        await self._assert_supervisor(project_id, supervisor_user_id)

        current = project.current_stage

        # Validate from_stage matches current stage
        if from_stage != current:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"from_stage '{from_stage}' does not match current stage '{current}'",
            )

        # Validate to_stage is a valid transition
        expected_next = _VALID_TRANSITIONS.get(current)
        if expected_next is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot advance from stage '{current}' — already at final stage",
            )
        if to_stage != expected_next:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid transition: '{current}' → '{to_stage}'. Expected '{expected_next}'",
            )

        # Canvas snapshot
        canvas_snapshot = await canvas_ops.get_canvas_state(project_id)

        # Duration: time since last stage_history entry or project creation
        duration_seconds = await self._compute_duration(project_id, project.created_at)

        # Write stage_history
        history_record = await self.repo.create(
            project_id=project_id,
            from_stage=current,
            to_stage=to_stage,
            triggered_by=triggered_by,
            canvas_snapshot=canvas_snapshot,
            duration_seconds=duration_seconds,
        )

        # Update project.current_stage
        project.current_stage = to_stage
        project.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

        # Broadcast
        event = StageChangedEvent(
            project_id=project_id,
            from_stage=current,
            to=to_stage,
            triggered_by=triggered_by,
        )
        await event_bus.publish(event)

        logger.info(
            "Project %s advanced stage %s → %s by %s",
            project_id,
            current,
            to_stage,
            triggered_by,
        )
        return AdvanceStageResponse(
            current_stage=to_stage,
            previous_snapshot_id=history_record.id,
        )

    async def list_history(self, project_id: UUID) -> list[StageHistoryResponse]:
        await self._get_project_or_404(project_id)
        records = await self.repo.list_by_project(project_id)
        return [
            StageHistoryResponse(
                id=r.id,
                project_id=r.project_id,
                from_stage=r.from_stage,
                to_stage=r.to_stage,
                triggered_by=r.triggered_by,
                canvas_snapshot=r.canvas_snapshot,
                duration_seconds=r.duration_seconds,
                created_at=r.created_at,
            )
            for r in records
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_project_or_404(self, project_id: UUID) -> Project:
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        return project

    async def _assert_supervisor(self, project_id: UUID, user_id: UUID) -> None:
        """Raise 403 if user does not occupy the supervisor seat."""
        result = await self.session.execute(
            select(Seat).where(
                Seat.project_id == project_id,
                Seat.seat_role == "supervisor",
                Seat.occupant_type == "human",
                Seat.user_id == user_id,
            )
        )
        seat = result.scalar_one_or_none()
        if seat is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the human supervisor may advance the stage",
            )

    async def _compute_duration(
        self, project_id: UUID, project_created_at: datetime
    ) -> int | None:
        """Compute seconds spent in current stage."""
        try:
            result = await self.session.execute(
                select(StageHistory)
                .where(StageHistory.project_id == project_id)
                .order_by(StageHistory.created_at.desc())
                .limit(1)
            )
            last_entry = result.scalar_one_or_none()
            reference = last_entry.created_at if last_entry else project_created_at
            if reference.tzinfo is None:
                reference = reference.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - reference
            return int(delta.total_seconds())
        except Exception as exc:
            logger.warning("Could not compute stage duration: %s", exc)
            return None
