"""Evaluator guidance helpers — 從 evaluator.py 抽取以維持行數限制。

包含 Supervisor 聊天引導、盲區挑戰、弱項引導邏輯。
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from app.agents.blackboard import BlackboardManager

logger = logging.getLogger(__name__)

# Natural language mapping for internal evaluation terms
_NATURAL_GUIDANCE: dict[str, str] = {
    "盲區分數不足": "我們目前討論的面向可能還不夠多元，有沒有人想從不同角度切入？",
    "內容多樣性": "大家的觀點蠻集中的，我們試試看從其他使用者族群的角度來想？",
    "討論深度": "目前的討論還停在表面，我們能不能再深入追問「為什麼」？",
    "收斂程度": "觀點開始重複了，或許我們可以開始整理歸納了。",
}


async def publish_supervisor_message(
    project_id: UUID, agent_id: str, content_raw: str,
) -> None:
    """Publish a Supervisor chat message (with Chinese conversion)."""
    from app.events.types import ChatMessageEvent
    from app.events.bus import event_bus
    from app.chinese.converter import chinese_converter
    from app.agents.personas.display import resolve_display_name

    event = ChatMessageEvent(
        project_id=project_id,
        sender_id=agent_id,
        sender_type="ai",
        sender_name=resolve_display_name("supervisor"),
        content=chinese_converter.convert(content_raw),
    )
    await event_bus.publish(event)


async def publish_blind_spot_challenge(project_id: UUID, agent_id: str) -> None:
    """Send a 'final call' asking team to identify missed perspectives."""
    try:
        await publish_supervisor_message(
            project_id, agent_id,
            "在我們準備往下走之前，讓我確認一下——"
            "我們是不是還漏了什麼重要的面向？"
            "還有沒有我們沒想到的？",
        )
        logger.info("Published blind spot challenge for project %s", project_id)
    except Exception as exc:
        logger.error("Failed to publish blind spot challenge: %s", exc)


async def publish_weak_area_guidance(
    weak_areas: list[str],
    project_id: UUID,
    agent_id: str,
    blackboard: BlackboardManager,
    last_guidance_text: str,
    last_guidance_time: float,
    crew_responded_since_guidance: bool,
) -> tuple[str, float, bool]:
    """Publish chat message guiding team to improve weak areas.

    Returns updated (last_guidance_text, last_guidance_time, crew_responded_since_guidance).
    """
    if not weak_areas:
        return last_guidance_text, last_guidance_time, crew_responded_since_guidance
    try:
        primary_area = weak_areas[0]

        # Skip internal-only messages
        if "尚未達到質性分析門檻" in primary_area:
            return last_guidance_text, last_guidance_time, crew_responded_since_guidance

        now = time.time()

        # Cooldown dedup
        if primary_area == last_guidance_text and (now - last_guidance_time) < 300:
            return last_guidance_text, last_guidance_time, crew_responded_since_guidance

        # Skip if no Crew responded since last guidance
        if last_guidance_time > 0 and not crew_responded_since_guidance:
            logger.debug("Skipping guidance — no Crew response since last guidance")
            return last_guidance_text, last_guidance_time, crew_responded_since_guidance

        # Convert internal terminology to natural language
        message = _NATURAL_GUIDANCE.get(primary_area)
        if not message:
            for key, natural in _NATURAL_GUIDANCE.items():
                if key in primary_area:
                    message = natural
                    break
        if not message:
            message = (
                f"我覺得我們在「{primary_area}」方面可以再深入探討一些，"
                f"大家有什麼想法嗎？"
            )

        await publish_supervisor_message(project_id, agent_id, message)

        # Also write a Blackboard directive
        from app.agents.blackboard_schemas import CoordinationDirective
        directive = CoordinationDirective(
            round_type="focused_discuss",
            focus_topic=primary_area,
            invited_speaker="all_crew",
            instruction=message,
            ttl_seconds=60.0,
        )
        await blackboard.write_coordination_directive(directive)

        logger.info(
            "Published weak-area guidance + directive for project %s: %s",
            project_id, primary_area,
        )
        return primary_area, now, False
    except Exception as exc:
        logger.error("Failed to publish weak-area guidance: %s", exc)
        return last_guidance_text, last_guidance_time, crew_responded_since_guidance
