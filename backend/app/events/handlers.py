"""
Event handlers for routing events to AI agents.

Pushes chat messages into the Redis context buffer so agents
pick them up faster (within their next 1-second decision cycle)
instead of waiting for the slower DB poll.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)


async def handle_chat_message(
    project_id: UUID, sender_id: str, content: str
) -> None:
    """Push chat message into Redis context buffer for faster agent pickup."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        key = f"project:{project_id}:chat_events"
        event = json.dumps(
            {
                "sender": sender_id,
                "content": content,
                "time": datetime.now(timezone.utc).strftime("%H:%M"),
            }
        )
        await r.rpush(key, event)
        await r.ltrim(key, -30, -1)  # keep last 30 messages
        await r.aclose()
    except Exception as exc:
        logger.warning("handle_chat_message failed: %s", exc)
