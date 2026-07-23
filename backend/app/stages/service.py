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
from app.db.models.stage_history import StageHistory
from app.db.models.user import User
from app.events.bus import event_bus
from app.events.types import MicroPhaseChangedEvent, StageChangedEvent
from app.stages.micro_phase_repository import MicroPhaseHistoryRepository
from app.stages.micro_phases import (
    get_first_micro_phase_for_stage,
    get_macro_stage,
    is_backtrack,
    is_macro_boundary,
    validate_advance,
    validate_backtrack,
)
from app.stages.repository import StageHistoryRepository
from app.stages.schemas import (
    AdvanceMicroPhaseResponse,
    AdvanceStageResponse,
    MicroPhaseHistoryResponse,
    StageHistoryResponse,
    StageResponse,
)

logger = logging.getLogger(__name__)

# Valid DT stage transitions (first diamond only; define → completed is the terminal transition)
_VALID_TRANSITIONS: dict[str, str] = {
    "discover": "define",
    "define": "completed",
}


class StageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = StageHistoryRepository(session)
        self.micro_repo = MicroPhaseHistoryRepository(session)

    async def get_stage(self, project_id: UUID) -> StageResponse:
        project = await self._get_project_or_404(project_id)
        return StageResponse(
            project_id=project.id,
            current_stage=project.current_stage,
            current_micro_phase=project.current_micro_phase,
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

        # Canvas snapshot (Phase 16: use get_canvas_snapshot for full data)
        try:
            from app.canvas.tools_perception import get_canvas_snapshot
            canvas_snapshot = await get_canvas_snapshot(project_id)
        except Exception:
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

        # Update project.current_stage + reset micro_phase (P0-5)
        project.current_stage = to_stage
        old_micro_phase = project.current_micro_phase or "1.1"
        first_micro = get_first_micro_phase_for_stage(to_stage)
        if first_micro:
            project.current_micro_phase = first_micro
        project.updated_at = datetime.now(timezone.utc)

        # Write MicroPhaseHistory for correct duration tracking (P0-6)
        if first_micro and old_micro_phase != first_micro:
            from app.db.models.micro_phase_history import MicroPhaseHistory
            mph = MicroPhaseHistory(
                project_id=project_id,
                from_micro_phase=old_micro_phase,
                to_micro_phase=first_micro,
                transition_type="stage_advance",
                triggered_by=str(triggered_by),
            )
            self.session.add(mph)

        await self.session.commit()

        # Broadcast stage change
        event = StageChangedEvent(
            project_id=project_id,
            from_stage=current,
            to=to_stage,
            triggered_by=triggered_by,
        )
        await event_bus.publish(event)

        # Broadcast micro_phase change (P0-7)
        if first_micro and old_micro_phase != first_micro:
            await event_bus.publish(MicroPhaseChangedEvent(
                project_id=project_id,
                from_phase=old_micro_phase,
                to_phase=first_micro,
                transition_type="stage_advance",
                triggered_by=str(triggered_by),
            ))

        logger.info(
            "Project %s advanced stage %s → %s (micro_phase %s → %s) by %s",
            project_id,
            current,
            to_stage,
            old_micro_phase,
            first_micro,
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

    async def advance_micro_phase(
        self,
        project_id: UUID,
        from_phase: str,
        to_phase: str,
        triggered_by: str,
        reason: str | None = None,
    ) -> AdvanceMicroPhaseResponse:
        """Advance or backtrack the micro phase; supervisor only."""
        project = await self._get_project_or_404(project_id)

        if project.current_micro_phase != from_phase:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"from_phase '{from_phase}' does not match "
                    f"current micro phase '{project.current_micro_phase}'"
                ),
            )

        backtrack = is_backtrack(from_phase, to_phase)

        if backtrack:
            valid = validate_backtrack(from_phase, to_phase)
        else:
            valid = validate_advance(from_phase, to_phase)

        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid micro phase transition: '{from_phase}' → '{to_phase}'",
            )

        transition_type = "backtrack" if backtrack else "advance"

        duration_seconds = await self._compute_micro_phase_duration(project_id, project.created_at)

        project.current_micro_phase = to_phase
        project.updated_at = datetime.now(timezone.utc)

        macro_boundary = is_macro_boundary(from_phase, to_phase)
        old_macro_stage = project.current_stage
        if macro_boundary:
            project.current_stage = get_macro_stage(to_phase)

        await self.micro_repo.create(
            project_id=project_id,
            from_micro_phase=from_phase,
            to_micro_phase=to_phase,
            transition_type=transition_type,
            triggered_by=triggered_by,
            reason=reason,
            duration_seconds=duration_seconds,
        )

        await self.session.commit()

        micro_event = MicroPhaseChangedEvent(
            project_id=project_id,
            from_phase=from_phase,
            to_phase=to_phase,
            transition_type=transition_type,
            triggered_by=triggered_by,
        )
        await event_bus.publish(micro_event)

        if macro_boundary:
            stage_event = StageChangedEvent(
                project_id=project_id,
                from_stage=old_macro_stage,
                to=project.current_stage,
                triggered_by=triggered_by,
            )
            await event_bus.publish(stage_event)

        logger.info(
            "Project %s micro phase %s → %s (%s) by %s",
            project_id,
            from_phase,
            to_phase,
            transition_type,
            triggered_by,
        )
        return AdvanceMicroPhaseResponse(
            current_micro_phase=to_phase,
            is_backtrack=backtrack,
        )

    async def list_micro_phase_history(
        self, project_id: UUID
    ) -> list[MicroPhaseHistoryResponse]:
        await self._get_project_or_404(project_id)
        records = await self.micro_repo.list_by_project(project_id)
        return [
            MicroPhaseHistoryResponse(
                id=r.id,
                project_id=r.project_id,
                from_micro_phase=r.from_micro_phase,
                to_micro_phase=r.to_micro_phase,
                transition_type=r.transition_type,
                triggered_by=r.triggered_by,
                reason=r.reason,
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
        """Raise 403 unless the caller is allowed to manually advance the stage.

        Since the Supervisor seat is AI-only (no human can occupy it), the only
        humans permitted to manually advance are teachers/admins who created the
        project. All other manual triggers must be denied — AI agents advance
        through internal evaluator paths, not this HTTP endpoint.
        """
        user_result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is not None and user.role in ("teacher", "admin"):
            project_result = await self.session.execute(
                select(Project).where(Project.id == project_id)
            )
            project = project_result.scalar_one_or_none()
            if project is not None and project.creator_id == user.id:
                return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Stage advancement is restricted: the Supervisor seat is "
                "AI-only, and only the project's teacher/admin creator may "
                "force-advance manually."
            ),
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

    async def _compute_micro_phase_duration(
        self, project_id: UUID, project_created_at: datetime
    ) -> int | None:
        """Compute seconds spent in current micro phase."""
        from app.db.models.micro_phase_history import MicroPhaseHistory

        try:
            result = await self.session.execute(
                select(MicroPhaseHistory)
                .where(MicroPhaseHistory.project_id == project_id)
                .order_by(MicroPhaseHistory.created_at.desc())
                .limit(1)
            )
            last_entry = result.scalar_one_or_none()
            reference = last_entry.created_at if last_entry else project_created_at
            if reference.tzinfo is None:
                reference = reference.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - reference
            return int(delta.total_seconds())
        except Exception as exc:
            logger.warning("Could not compute micro phase duration: %s", exc)
            return None
