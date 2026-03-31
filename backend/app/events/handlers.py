"""
Event handlers for routing events to AI agents.

Pushes chat messages into the Redis context buffer so agents
pick them up faster (within their next 1-second decision cycle)
instead of waiting for the slower DB poll.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)


async def handle_chat_message(
    project_id: UUID,
    sender_id: str,
    content: str,
    sender_name: str = "",
    sender_type: str = "human",
) -> None:
    """Push chat message into Redis context buffer and update conversation state."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            key = f"project:{project_id}:chat_events"
            event = json.dumps(
                {
                    "sender": f"{sender_name or sender_id}({sender_type})",
                    "sender_type": sender_type,
                    "content": content,
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                }
            )
            await r.rpush(key, event)
            await r.ltrim(key, -30, -1)  # keep last 30 messages
            # Update last event timestamp for agent ASSESS Rule 5 (idle detection)
            await r.set(f"project:{project_id}:last_event_ts", str(time.time()))
        finally:
            await r.aclose()
    except Exception as exc:
        logger.warning("handle_chat_message Redis push failed: %s", exc)

    # Update conversation state tracker for ALL messages (human + AI)
    try:
        from app.agents.conversation_state import ConversationStateTracker
        from app.agents.utils import load_seat_roles

        tracker = ConversationStateTracker(project_id)
        all_seats = await load_seat_roles(project_id)
        await tracker.update_on_message(sender_name or sender_id, content, all_seats)
    except Exception as exc:
        logger.warning("Conversation state update failed: %s", exc)
