from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.seat import Seat
from app.db.models.user import User
from app.projects.repository import ProjectRepository
from app.projects.schemas import (
    JoinRequest,
    JoinResponse,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectResponse,
    ProjectUpdateRequest,
    SeatResponse,
)
from app.seats.manager import seat_manager

logger = logging.getLogger(__name__)

SEAT_ROLES = ["supervisor", "crew_1", "crew_2", "crew_3", "crew_4"]


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.repo = ProjectRepository(session)
        self.session = session

    async def create_project(
        self, request: ProjectCreateRequest, user: User
    ) -> ProjectResponse:
        if user.role == "student" and not user.can_create_project:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to create projects",
            )

        project = Project(
            name=request.name,
            description=request.description,
            creator_id=user.id,
            ai_contribution=request.ai_contribution,
        )
        project = await self.repo.create(project)

        seats = []
        for role in SEAT_ROLES:
            seat = Seat(
                project_id=project.id,
                seat_role=role,
                occupant_type="ai",
                agent_id=f"agent_{role}",
                state="ai_running",
            )
            self.session.add(seat)
            seats.append(seat)
        await self.session.flush()

        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
        )

    async def list_projects(self, user: User) -> list[ProjectListItem]:
        projects = await self.repo.list_user_projects(user.id)
        result = []
        for p in projects:
            seats = await self.repo.get_seats(p.id)
            human_count = sum(1 for s in seats if s.occupant_type == "human")
            ai_count = sum(1 for s in seats if s.occupant_type == "ai")
            result.append(
                ProjectListItem(
                    id=p.id,
                    name=p.name,
                    current_stage=p.current_stage,
                    status=p.status,
                    seat_summary={"human": human_count, "ai": ai_count},
                    updated_at=p.updated_at,
                )
            )
        return result

    async def get_project(self, project_id: UUID) -> ProjectResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        seats = await self.repo.get_seats(project_id)
        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
        )

    async def update_project(
        self, project_id: UUID, request: ProjectUpdateRequest, user: User
    ) -> ProjectResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        if project.creator_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator may update this project",
            )
        if request.name is not None:
            project.name = request.name
        if request.description is not None:
            project.description = request.description
        if request.ai_contribution is not None:
            project.ai_contribution = request.ai_contribution
        project.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        seats = await self.repo.get_seats(project_id)
        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            current_stage=project.current_stage,
            ai_contribution=project.ai_contribution,
            status=project.status,
            creator_id=project.creator_id,
            seats=[self._seat_to_response(s) for s in seats],
            created_at=project.created_at,
        )

    async def get_seats(self, project_id: UUID) -> list[SeatResponse]:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        seats = await self.repo.get_seats(project_id)
        return [self._seat_to_response(s) for s in seats]

    async def join_project(
        self, project_id: UUID, request: JoinRequest, user: User
    ) -> JoinResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        seat = await self.repo.get_seat(project_id, request.seat_role)
        if not seat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid seat role"
            )
        if seat.occupant_type == "human":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Seat is already occupied by a human",
            )

        # Delegate to SeatManager: stops AI agent, updates DB/Redis, broadcasts event
        await seat_manager.assign_human(
            project_id=project_id,
            seat_role=request.seat_role,
            user_id=user.id,
            user_name=user.display_name,
        )

        # Ensure all other AI seats have running agents
        await seat_manager.start_all_agents(project_id)

        # Re-read seat from DB for the response (SeatManager committed via its own session)
        self.session.expire_all()
        seat = await self.repo.get_seat(project_id, request.seat_role)

        return JoinResponse(
            seat=self._seat_to_response(seat),
            workspace_url=f"/projects/{project_id}/workspace",
        )

    async def leave_project(self, project_id: UUID, user: User) -> dict:
        seats = await self.repo.get_seats(project_id)
        user_seat = next(
            (s for s in seats if s.user_id == user.id),
            None,
        )
        if not user_seat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are not in any seat",
            )

        # Delegate to SeatManager: updates DB/Redis, starts AI agent, sends greeting
        await seat_manager.release_human(
            project_id=project_id,
            seat_role=user_seat.seat_role,
        )

        return {"message": "Left successfully"}

    @staticmethod
    def _seat_to_response(seat: Seat) -> SeatResponse:
        display_name = None
        if seat.occupant_type == "ai":
            display_name = f"AI {seat.seat_role.replace('_', ' ').title()}"
        return SeatResponse(
            seat_role=seat.seat_role,
            occupant_type=seat.occupant_type,
            user_id=seat.user_id,
            agent_id=seat.agent_id,
            display_name=display_name,
        )
