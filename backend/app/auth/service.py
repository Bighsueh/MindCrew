from uuid import UUID

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.schemas import RegisterRequest, LoginRequest, RefreshRequest, TokenResponse, UserResponse
from app.db.models.user import User


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


async def _verify_password_async(password: str, hashed: str) -> bool:
    """Run bcrypt verification in a thread so it doesn't block the event loop.

    bcrypt.checkpw is CPU-bound (~50-100ms). When the server is under load
    (many active agent loops), running it synchronously on the asyncio loop
    starves health-checks and other coroutines, which surfaces as intermittent
    HTTP 500 on /api/auth/login during peak agent activity.
    """
    import asyncio
    return await asyncio.to_thread(_verify_password, password, hashed)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register(self, request: RegisterRequest) -> TokenResponse:
        result = await self.session.execute(
            select(User).where(User.email == request.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user = User(
            email=request.email,
            password_hash=_hash_password(request.password),
            display_name=request.display_name,
            role="teacher",
            can_create_project=True,
        )
        self.session.add(user)
        await self.session.flush()

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserResponse.model_validate(user),
        )

    async def login(self, request: LoginRequest) -> TokenResponse:
        result = await self.session.execute(
            select(User).where(User.email == request.email)
        )
        user = result.scalar_one_or_none()
        if not user or not await _verify_password_async(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserResponse.model_validate(user),
        )

    async def refresh(self, request: RefreshRequest) -> TokenResponse:
        payload = decode_token(request.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        user_id = payload.get("sub")
        result = await self.session.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserResponse.model_validate(user),
        )
