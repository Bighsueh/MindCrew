from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str
    role: Literal["teacher", "student"] = "teacher"


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    can_create_project: bool
    # Phase 22：教師專屬簽名碼，供學生於建立活動時輸入以列管
    signature_code: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse
