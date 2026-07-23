"""Resolve the billing/owning user for a project's autonomous LLM calls.

Single source of truth shared by the seat manager (agent ticks) and the
first-diamond closing ritual. Every ``llm_request_logs`` row requires a
NOT-NULL ``owning_user_id`` (Phase 25.J); callers without a direct human
``triggered_by`` use this to attribute the spend.

The body was lifted verbatim from ``SeatManager._resolve_owning_user`` so
both call sites agree on the same fallback chain.
"""
from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db.models.project import Project
from app.db.models.user import User
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def resolve_owning_user(project_id: UUID) -> UUID:
    """Pick the user that owns LLM calls fired by this project's agents.

    Autonomous agent ticks have no human ``triggered_by_user_id``, so the
    token usage is attributed to whoever this returns. We deliberately use
    the project **creator** — the real user running the project — rather
    than the linked teacher, so per-user stats reflect actual consumers.

    Strategy:
      1. project.creator_id (NOT NULL) — the user who created/owns the
         project. This is the normal path.
      2. seeded admin user — last-resort fallback only when the project
         row can't be loaded, so the NOT NULL FK on llm_request_logs is
         always satisfied.

    Note: an earlier version read a non-existent ``project.owner_id`` via
    ``getattr(..., None)``, which always returned None and dumped every
    teacher-less project's agent tokens onto the admin account.
    """
    try:
        async with async_session_factory() as session:
            project = (
                await session.execute(select(Project).where(Project.id == project_id))
            ).scalar_one_or_none()
            if project is not None and project.creator_id is not None:
                return project.creator_id
            admin = (
                await session.execute(
                    select(User).where(User.role == "admin").limit(1)
                )
            ).scalar_one_or_none()
            if admin is not None:
                return admin.id
    except Exception as exc:
        logger.warning("resolve_owning_user fallback (%s): %s", project_id, exc)
    # Final fallback: return a known-bad uuid. log_service will fail to
    # insert and warn, but the critical path stays up.
    return uuid4()


__all__ = ["resolve_owning_user"]
