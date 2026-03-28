from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.seat import Seat


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, project_id: UUID) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def create(self, project: Project) -> Project:
        self.session.add(project)
        await self.session.flush()
        return project

    async def list_by_user(self, user_id: UUID) -> list[Project]:
        result = await self.session.execute(
            select(Project)
            .where(Project.creator_id == user_id)
            .order_by(Project.updated_at.desc())
        )
        return list(result.scalars().all())

    async def list_user_projects(self, user_id: UUID) -> list[Project]:
        """Get projects where user is creator or occupies a seat."""
        from sqlalchemy import or_, exists

        seat_subq = (
            select(Seat.project_id)
            .where(Seat.user_id == user_id)
            .correlate(Project)
            .exists()
        )
        result = await self.session.execute(
            select(Project)
            .where(or_(Project.creator_id == user_id, seat_subq))
            .order_by(Project.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_seats(self, project_id: UUID) -> list[Seat]:
        result = await self.session.execute(
            select(Seat).where(Seat.project_id == project_id).order_by(Seat.seat_role)
        )
        return list(result.scalars().all())

    async def get_seat(self, project_id: UUID, seat_role: str) -> Seat | None:
        result = await self.session.execute(
            select(Seat).where(
                Seat.project_id == project_id, Seat.seat_role == seat_role
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, project: Project) -> None:
        await self.session.delete(project)
        await self.session.flush()
