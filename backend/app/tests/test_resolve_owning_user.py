"""Attribution fix: autonomous agent LLM calls must be owned by the project
**creator** (the real user running the project), not the admin fallback.

Regression guard for the bug where ``_resolve_owning_user`` read a
non-existent ``project.owner_id`` and dumped every teacher-less project's
agent tokens onto the seeded admin account.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.user import User
from app.llm.owning_user import resolve_owning_user
from app.seats.manager import SeatManager

pytestmark = pytest.mark.asyncio


def _user(role: str, email: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash="x",
        display_name=role.title(),
        role=role,
    )


def _project(creator_id: uuid.UUID, teacher_id: uuid.UUID | None = None) -> Project:
    return Project(
        id=uuid.uuid4(),
        name="P",
        creator_id=creator_id,
        linked_teacher_id=teacher_id,
        invite_code=uuid.uuid4().hex[:8],
    )


@pytest_asyncio.fixture
def patch_factory(monkeypatch):
    """Point the manager's session factory at the test ``db_session`` without
    closing it on context exit (the fixture owns the lifecycle)."""

    def _install(session: AsyncSession) -> None:
        @asynccontextmanager
        async def _factory():
            yield session

        # The session is opened inside the shared resolver now (the manager
        # method is a thin wrapper), so patch there — patching the manager
        # module would be a no-op and hit the real DB.
        monkeypatch.setattr("app.llm.owning_user.async_session_factory", _factory)

    return _install


async def test_attributes_to_creator_when_no_teacher(
    db_session: AsyncSession, patch_factory
) -> None:
    creator = _user("student", "creator@example.com")
    admin = _user("admin", "admin@example.com")
    db_session.add_all([creator, admin])
    await db_session.flush()
    project = _project(creator_id=creator.id)
    db_session.add(project)
    await db_session.flush()
    patch_factory(db_session)

    owning = await SeatManager()._resolve_owning_user(project.id)

    assert owning == creator.id


async def test_creator_preferred_over_linked_teacher(
    db_session: AsyncSession, patch_factory
) -> None:
    creator = _user("student", "creator2@example.com")
    teacher = _user("teacher", "teacher@example.com")
    db_session.add_all([creator, teacher])
    await db_session.flush()
    project = _project(creator_id=creator.id, teacher_id=teacher.id)
    db_session.add(project)
    await db_session.flush()
    patch_factory(db_session)

    owning = await SeatManager()._resolve_owning_user(project.id)

    # The real consumer is the creator; teacher must NOT absorb agent tokens.
    assert owning == creator.id
    assert owning != teacher.id


async def test_admin_fallback_when_project_missing(
    db_session: AsyncSession, patch_factory
) -> None:
    admin = _user("admin", "admin3@example.com")
    db_session.add(admin)
    await db_session.flush()
    patch_factory(db_session)

    owning = await SeatManager()._resolve_owning_user(uuid.uuid4())

    assert owning == admin.id


async def test_shared_resolver_returns_creator(
    db_session: AsyncSession, patch_factory
) -> None:
    """The shared resolver (used directly by the closing ritual) resolves the
    creator without going through SeatManager."""
    creator = _user("student", "creator4@example.com")
    db_session.add(creator)
    await db_session.flush()
    project = _project(creator_id=creator.id)
    db_session.add(project)
    await db_session.flush()
    patch_factory(db_session)

    owning = await resolve_owning_user(project.id)

    assert owning == creator.id
