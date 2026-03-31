"""Blackboard writer — 將 ThinkResult 的意圖寫入 Redis Blackboard。

從 base_agent.py 抽取以維持行數限制。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.blackboard import BlackboardManager
from app.agents.blackboard_schemas import AgentIntention

logger = logging.getLogger(__name__)


async def write_intention_from_think_result(
    blackboard: BlackboardManager,
    think_result: Any,
    context: dict,
    agent_id: str,
    seat_role: str,
) -> None:
    """Extract reasoning + intent from ThinkResult and write to Blackboard."""
    try:
        focus_topic: str | None = None
        viewpoint: str | None = None
        next_intent = "no_action"

        for action in think_result.actions:
            atype = action.get("type", "no_action")
            if atype != "no_action":
                next_intent = atype
                if atype in ("create_note", "chat_message"):
                    focus_topic = action.get("content", "")[:50]
                break

        # Try to extract focus_topic/viewpoint from raw JSON response
        try:
            raw_data = json.loads(think_result.raw_response.strip().strip("`").strip())
            focus_topic = raw_data.get("focus_topic", focus_topic)
            viewpoint = raw_data.get("viewpoint", viewpoint)
        except Exception:
            pass

        intention = AgentIntention(
            agent_id=agent_id,
            seat_role=seat_role,
            reasoning_summary=think_result.reasoning[:200] if think_result.reasoning else "",
            next_intent=next_intent,
            focus_topic=focus_topic,
            viewpoint=viewpoint,
            confidence=0.7,
            stage=context.get("current_stage", "discover"),
        )
        await blackboard.write_intention(intention)
    except Exception:
        logger.warning("Failed to write blackboard for %s", agent_id, exc_info=True)
