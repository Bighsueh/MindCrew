"""Seat service: bridges HTTP endpoints to the SeatManager."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.seat import Seat
from app.db.models.user import User
from app.seats.manager import seat_manager

logger = logging.getLogger(__name__)


class SeatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def take_seat(
        self,
        project_id: UUID,
        seat_role: str,
        current_user: User,
    ) -> dict:
        """Human user takes over a seat (replaces AI)."""
        project = await self._get_project_or_404(project_id)
        seat = await self._get_seat_or_400(project_id, seat_role)

        if seat.occupant_type == "human" and seat.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Seat is already occupied by another human",
            )

        await seat_manager.assign_human(
            project_id=project_id,
            seat_role=seat_role,
            user_id=current_user.id,
            user_name=current_user.display_name,
        )

        return {
            "project_id": str(project_id),
            "seat_role": seat_role,
            "occupant_type": "human",
            "user_id": str(current_user.id),
        }

    async def release_seat(
        self,
        project_id: UUID,
        seat_role: str,
        current_user: User,
    ) -> dict:
        """Human user releases a seat back to AI."""
        await self._get_project_or_404(project_id)
        seat = await self._get_seat_or_400(project_id, seat_role)

        if seat.occupant_type != "human" or seat.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are not currently occupying this seat",
            )

        await seat_manager.release_human(
            project_id=project_id,
            seat_role=seat_role,
        )

        return {
            "project_id": str(project_id),
            "seat_role": seat_role,
            "occupant_type": "ai",
        }

    async def list_seats(self, project_id: UUID) -> list[dict]:
        """Return current seat state for a project."""
        result = await self.session.execute(
            select(Seat).where(Seat.project_id == project_id).order_by(Seat.seat_role)
        )
        seats = result.scalars().all()
        return [
            {
                "seat_role": s.seat_role,
                "occupant_type": s.occupant_type,
                "user_id": str(s.user_id) if s.user_id else None,
                "agent_id": s.agent_id,
                "state": s.state,
            }
            for s in seats
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

    async def _get_seat_or_400(self, project_id: UUID, seat_role: str) -> Seat:
        result = await self.session.execute(
            select(Seat).where(
                Seat.project_id == project_id,
                Seat.seat_role == seat_role,
            )
        )
        seat = result.scalar_one_or_none()
        if seat is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Seat '{seat_role}' does not exist in this project",
            )
        return seat
