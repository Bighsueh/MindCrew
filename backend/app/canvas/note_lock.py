"""Note-level locking for concurrency control.

Spec §3:
- Granularity: one note at a time
- First-come-first-served
- 15-second auto-release timeout
- Human overrides AI lock
"""

from __future__ import annotations

import logging
from uuid import UUID

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_LOCK_TTL = 15  # seconds
_LOCK_KEY = "canvas:{project_id}:lock:{note_id}"


class NoteLockManager:
    """Redis-backed note-level locks."""

    async def acquire(
        self,
        project_id: UUID,
        note_id: str,
        holder_id: str,
        holder_type: str = "ai",
    ) -> bool:
        """Try to acquire a lock. Returns True if successful."""
        key = _LOCK_KEY.format(project_id=project_id, note_id=note_id)
        value = f"{holder_type}:{holder_id}"
        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            acquired = await r.set(key, value, nx=True, ex=_LOCK_TTL)
            await r.aclose()
            return bool(acquired)
        except Exception:
            logger.debug("Lock acquire failed for %s", key)
            return False

    async def release(
        self,
        project_id: UUID,
        note_id: str,
        holder_id: str,
    ) -> None:
        """Release a lock if held by the given holder."""
        key = _LOCK_KEY.format(project_id=project_id, note_id=note_id)
        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            current = await r.get(key)
            if current and current.endswith(f":{holder_id}"):
                await r.delete(key)
            await r.aclose()
        except Exception:
            logger.debug("Lock release failed for %s", key)

    async def force_release(
        self,
        project_id: UUID,
        note_id: str,
    ) -> None:
        """Force-release a lock (for human override)."""
        key = _LOCK_KEY.format(project_id=project_id, note_id=note_id)
        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await r.delete(key)
            await r.aclose()
        except Exception:
            logger.debug("Force release failed for %s", key)

    async def acquire_human_override(
        self,
        project_id: UUID,
        note_id: str,
        human_id: str,
    ) -> bool:
        """Human acquires lock, overriding any AI lock."""
        key = _LOCK_KEY.format(project_id=project_id, note_id=note_id)
        value = f"human:{human_id}"
        try:
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            current = await r.get(key)
            if current and current.startswith("ai:"):
                # Override AI lock
                await r.set(key, value, ex=_LOCK_TTL)
                await r.aclose()
                return True
            if current is None:
                acquired = await r.set(key, value, nx=True, ex=_LOCK_TTL)
                await r.aclose()
                return bool(acquired)
            await r.aclose()
            return False
        except Exception:
            logger.debug("Human override failed for %s", key)
            return False


note_lock_manager = NoteLockManager()
