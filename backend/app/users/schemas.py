from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateStudentRequest(BaseModel):
    email: str
    password: str
    display_name: str
    can_create_project: bool = False


class StudentResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    can_create_project: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdatePermissionRequest(BaseModel):
    can_create_project: bool
