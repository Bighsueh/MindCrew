from uuid import UUID

from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.users.repository import UserRepository
from app.users.schemas import CreateStudentRequest, StudentResponse, UpdatePermissionRequest

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, session: AsyncSession):
        self.repo = UserRepository(session)

    async def create_student(
        self, request: CreateStudentRequest, teacher: User
    ) -> StudentResponse:
        if teacher.role != "teacher":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only teachers can create students",
            )
        existing = await self.repo.get_by_email(request.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        student = User(
            email=request.email,
            password_hash=pwd_context.hash(request.password),
            display_name=request.display_name,
            role="student",
            can_create_project=request.can_create_project,
            created_by=teacher.id,
        )
        student = await self.repo.create(student)
        return StudentResponse.model_validate(student)

    async def list_students(self, teacher: User) -> list[StudentResponse]:
        if teacher.role != "teacher":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only teachers can list students",
            )
        students = await self.repo.get_students_by_teacher(teacher.id)
        return [StudentResponse.model_validate(s) for s in students]

    async def update_permission(
        self, student_id: UUID, request: UpdatePermissionRequest, teacher: User
    ) -> StudentResponse:
        if teacher.role != "teacher":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only teachers can update student permissions",
            )
        student = await self.repo.get_by_id(student_id)
        if not student or student.created_by != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found",
            )
        student.can_create_project = request.can_create_project
        await self.repo.session.flush()
        return StudentResponse.model_validate(student)
