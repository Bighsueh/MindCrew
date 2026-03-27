"""Shared utility functions for the agent subsystem."""
from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def load_seat_roles(project_id: UUID) -> list[str]:
    """Load all seat role names for a project (used for addressee detection)."""
    try:
        from sqlalchemy import select

        from app.db.models.seat import Seat
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            rows = await session.execute(
                select(Seat.seat_role).where(Seat.project_id == project_id)
            )
            return [r[0] for r in rows.all()]
    except Exception as exc:
        logger.warning("load_seat_roles failed: %s", exc)
        return []
