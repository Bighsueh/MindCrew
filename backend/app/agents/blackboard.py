"""Blackboard Manager — Redis read/write layer for agent coordination.

See docs/blackboard-design.md §2 (key structure) and §4 (read/write flow).
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import redis.asyncio as aioredis

from app.agents.blackboard_schemas import (
    AgentIntention,
    Coordination,
    CoordinationDirective,
    TopicSaturation,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Redis key templates (§2)
_KEY_INTENTION = "blackboard:{project_id}:agent:{agent_id}:intention"
_KEY_TOPIC_SATURATION = "blackboard:{project_id}:topic_saturation"
_KEY_COORDINATION = "blackboard:{project_id}:coordination"
_KEY_DIRECTIVE = "blackboard:{project_id}:coordination_directive"

# Seat registry key (shared with SeatManager / ContextBuffer)
_KEY_SEAT_EVENTS = "project:{project_id}:seat_events"

# TTL constants (§2)
_TTL_INTENTION_MIXED = 120
_TTL_INTENTION_ALL_AI = 30
_TTL_COORDINATION_MIXED = 60
_TTL_COORDINATION_ALL_AI = 15


class BlackboardManager:
    """Read/write interface to the Blackboard Redis layer for a single agent."""

    def __init__(
        self,
        project_id: UUID,
        agent_id: str,
        seat_role: str,
    ) -> None:
        self._project_id = project_id
        self._agent_id = agent_id
        self._seat_role = seat_role
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True
            )
        return self._redis

    # ------------------------------------------------------------------
    # Intention write / read
    # ------------------------------------------------------------------

    async def write_intention(self, intention: AgentIntention) -> None:
        """Write this agent's intention to Redis with appropriate TTL."""
        r = await self._get_redis()
        key = _KEY_INTENTION.format(
            project_id=self._project_id, agent_id=self._agent_id
        )
        ttl = await self._intention_ttl()
        await r.set(key, intention.model_dump_json(), ex=ttl)
        logger.debug(
            "Blackboard: wrote intention for %s (TTL %ds)", self._agent_id, ttl
        )

    async def read_other_intentions(self) -> list[AgentIntention]:
        """Read all other active AI agents' intentions (skip self + inactive)."""
        r = await self._get_redis()
        result: list[AgentIntention] = []

        seat_keys = await self._get_ai_seat_agent_ids()
        for other_agent_id in seat_keys:
            if other_agent_id == self._agent_id:
                continue
            key = _KEY_INTENTION.format(
                project_id=self._project_id, agent_id=other_agent_id
            )
            raw = await r.get(key)
            if not raw:
                continue
            try:
                intention = AgentIntention.model_validate_json(raw)
                if not intention.inactive:
                    result.append(intention)
            except Exception:
                logger.warning(
                    "Blackboard: failed to parse intention for %s",
                    other_agent_id,
                    exc_info=True,
                )
        return result

    # ------------------------------------------------------------------
    # Topic Saturation (written by Supervisor only)
    # ------------------------------------------------------------------

    async def read_topic_saturation(self) -> TopicSaturation | None:
        """Read the global topic saturation report."""
        r = await self._get_redis()
        key = _KEY_TOPIC_SATURATION.format(project_id=self._project_id)
        raw = await r.get(key)
        if not raw:
            return None
        try:
            return TopicSaturation.model_validate_json(raw)
        except Exception:
            logger.warning("Blackboard: failed to parse topic_saturation", exc_info=True)
            return None

    async def write_topic_saturation(self, saturation: TopicSaturation) -> None:
        """Write topic saturation (Supervisor only). No TTL — cleared on stage change."""
        r = await self._get_redis()
        key = _KEY_TOPIC_SATURATION.format(project_id=self._project_id)
        await r.set(key, saturation.model_dump_json())
        logger.debug("Blackboard: wrote topic_saturation for project %s", self._project_id)

    # ------------------------------------------------------------------
    # Coordination
    # ------------------------------------------------------------------

    async def read_coordination(self) -> Coordination | None:
        """Read the current coordination state."""
        r = await self._get_redis()
        key = _KEY_COORDINATION.format(project_id=self._project_id)
        raw = await r.get(key)
        if not raw:
            return None
        try:
            return Coordination.model_validate_json(raw)
        except Exception:
            logger.warning("Blackboard: failed to parse coordination", exc_info=True)
            return None

    async def write_coordination(self, coordination: Coordination) -> None:
        """Write coordination state with appropriate TTL."""
        r = await self._get_redis()
        key = _KEY_COORDINATION.format(project_id=self._project_id)
        ttl = await self._coordination_ttl()
        await r.set(key, coordination.model_dump_json(), ex=ttl)
        logger.debug(
            "Blackboard: wrote coordination for project %s (TTL %ds)",
            self._project_id,
            ttl,
        )

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    async def mark_inactive(self) -> None:
        """Mark this agent's intention as inactive (human takeover, §6)."""
        r = await self._get_redis()
        key = _KEY_INTENTION.format(
            project_id=self._project_id, agent_id=self._agent_id
        )
        raw = await r.get(key)
        if not raw:
            return
        try:
            intention = AgentIntention.model_validate_json(raw)
            updated = intention.model_copy(update={"inactive": True})
            ttl = await r.ttl(key)
            if ttl and ttl > 0:
                await r.set(key, updated.model_dump_json(), ex=ttl)
            else:
                await r.set(key, updated.model_dump_json(), ex=_TTL_INTENTION_MIXED)
            logger.info("Blackboard: marked %s as inactive", self._agent_id)
        except Exception:
            logger.warning(
                "Blackboard: failed to mark_inactive for %s",
                self._agent_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Coordination Directive (Solution B)
    # ------------------------------------------------------------------

    async def write_coordination_directive(
        self, directive: CoordinationDirective
    ) -> None:
        """Write a Supervisor directive. Crew agents read this before acting."""
        r = await self._get_redis()
        key = _KEY_DIRECTIVE.format(project_id=self._project_id)
        ttl = max(15, int(directive.ttl_seconds))
        await r.set(key, directive.model_dump_json(), ex=ttl)
        logger.info(
            "Blackboard: wrote directive round_type=%s focus=%s for project %s (TTL=%ds)",
            directive.round_type,
            directive.focus_topic,
            self._project_id,
            ttl,
        )

    async def read_coordination_directive(self) -> CoordinationDirective | None:
        """Read the current Supervisor directive. Returns None if expired."""
        r = await self._get_redis()
        key = _KEY_DIRECTIVE.format(project_id=self._project_id)
        raw = await r.get(key)
        if not raw:
            return None
        try:
            return CoordinationDirective.model_validate_json(raw)
        except Exception:
            logger.warning(
                "Blackboard: failed to parse directive for project %s",
                self._project_id,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def clear_stage(self, stage: str) -> None:
        """Clear topic_saturation on stage change or rollback (§6)."""
        r = await self._get_redis()
        key = _KEY_TOPIC_SATURATION.format(project_id=self._project_id)
        await r.delete(key)
        logger.info(
            "Blackboard: cleared topic_saturation for project %s (stage=%s)",
            self._project_id,
            stage,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_ai_seat_agent_ids(self) -> list[str]:
        """Return agent_id list for all AI-occupied seats in this project."""
        r = await self._get_redis()
        key = _KEY_SEAT_EVENTS.format(project_id=self._project_id)
        raw_list = await r.lrange(key, 0, -1)
        agent_ids: list[str] = []
        for raw in raw_list:
            try:
                seat = json.loads(raw) if isinstance(raw, str) else raw
                if seat.get("type") == "ai" and seat.get("agent_id"):
                    aid = seat["agent_id"]
                    if aid not in agent_ids:
                        agent_ids.append(aid)
            except Exception:
                continue
        return agent_ids

    async def _is_all_ai(self) -> bool:
        """Check if all seats are AI-occupied."""
        r = await self._get_redis()
        key = _KEY_SEAT_EVENTS.format(project_id=self._project_id)
        raw_list = await r.lrange(key, 0, -1)
        if not raw_list:
            return False
        for raw in raw_list:
            try:
                seat = json.loads(raw) if isinstance(raw, str) else raw
                if seat.get("type") != "ai":
                    return False
            except Exception:
                continue
        return True

    async def _intention_ttl(self) -> int:
        """Return the appropriate intention TTL based on mode."""
        if await self._is_all_ai():
            return _TTL_INTENTION_ALL_AI
        return _TTL_INTENTION_MIXED

    async def _coordination_ttl(self) -> int:
        """Return the appropriate coordination TTL based on mode."""
        if await self._is_all_ai():
            return _TTL_COORDINATION_ALL_AI
        return _TTL_COORDINATION_MIXED
