from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.users.schemas import CreateStudentRequest, StudentResponse, UpdatePermissionRequest
from app.users.service import UserService

router = APIRouter(prefix="/api/teacher", tags=["users"])


@router.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(
    request: CreateStudentRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StudentResponse:
    service = UserService(session)
    return await service.create_student(request, current_user)


@router.get("/students", response_model=list[StudentResponse])
async def list_students(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[StudentResponse]:
    service = UserService(session)
    return await service.list_students(current_user)


@router.patch("/students/{student_id}", response_model=StudentResponse)
async def update_permission(
    student_id: UUID,
    request: UpdatePermissionRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StudentResponse:
    service = UserService(session)
    return await service.update_permission(student_id, request, current_user)
