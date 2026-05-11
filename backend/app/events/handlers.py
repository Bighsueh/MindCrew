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
    chat_id: str | None = None,
) -> None:
    """Push chat message into Redis context buffer and update conversation state.

    依 spec/13-personal-chat.md §9.2：個人聊天**不可**寫入 Redis chat cache，
    避免 agent OBSERVE 路徑（context_buffer 讀同一把 key）撞到他人的私人訊息。
    僅 group / 向下相容 NULL 才會寫入 Redis；conversation state tracker 仍對
    所有訊息更新（個人聊天屬於該 user 自己的對話狀態，不外洩）。
    """
    # spec §9.2：personal chat 不進 Redis chat cache。
    from app.chat.chat_id import is_personal

    skip_redis_cache = is_personal(chat_id)

    if not skip_redis_cache:
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
    # 對個人聊天也要更新（屬該 user 的 dialog state；ConversationStateTracker
    # 內部不混入別人視野，不會造成洩漏）。
    try:
        from app.agents.conversation_state import ConversationStateTracker
        from app.agents.utils import load_seat_roles

        tracker = ConversationStateTracker(project_id)
        all_seats = await load_seat_roles(project_id)
        await tracker.update_on_message(sender_name or sender_id, content, all_seats)
    except Exception as exc:
        logger.warning("Conversation state update failed: %s", exc)
