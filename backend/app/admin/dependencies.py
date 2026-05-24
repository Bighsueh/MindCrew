"""FastAPI dependency that gates admin-only routes.

Reuses ``get_current_user`` from auth, then enforces ``role == 'admin'``.
A 403 (not 404) is returned to non-admins so the frontend can disambiguate
auth-vs-permission errors. Logged-out users still get 401 from the inner
``get_current_user`` call.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.auth.jwt import get_current_user
from app.db.models.user import User


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user
