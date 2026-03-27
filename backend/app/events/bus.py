from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator
from uuid import UUID

import redis.asyncio as aioredis

from app.config import settings
from app.events.types import AnyEvent

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "project"
_TEACHER_CHANNEL_PREFIX = "teacher"


def _project_channel(project_id: UUID) -> str:
    return f"{_CHANNEL_PREFIX}:{project_id}:events"


def _teacher_channel(user_id: UUID) -> str:
    return f"{_TEACHER_CHANNEL_PREFIX}:{user_id}:events"


class EventBus:
    """Redis Pub/Sub based event bus."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def initialize(self) -> None:
        self._redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        logger.info("EventBus initialised (Redis: %s)", settings.REDIS_URL)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            logger.info("EventBus closed")

    def _assert_ready(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("EventBus has not been initialised – call initialize() first")
        return self._redis

    async def publish(self, event: AnyEvent) -> None:
        r = self._assert_ready()
        channel = _project_channel(event.project_id)
        payload = event.to_json()
        await r.publish(channel, payload)
        logger.debug("Published event type=%s channel=%s", event.type, channel)

    async def publish_to_teacher(self, user_id: UUID, event: AnyEvent) -> None:
        r = self._assert_ready()
        channel = _teacher_channel(user_id)
        payload = event.to_json()
        await r.publish(channel, payload)
        logger.debug("Published teacher event type=%s channel=%s", event.type, channel)

    async def subscribe(self, project_id: UUID) -> AsyncGenerator[dict, None]:
        """Yield decoded event dicts from the project channel."""
        r = self._assert_ready()
        channel = _project_channel(project_id)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        logger.debug("Subscribed to channel=%s", channel)
        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                try:
                    data = json.loads(raw["data"])
                    yield data
                except json.JSONDecodeError:
                    logger.warning("Received non-JSON message on channel=%s", channel)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            logger.debug("Unsubscribed from channel=%s", channel)

    async def subscribe_teacher(self, user_id: UUID) -> AsyncGenerator[dict, None]:
        """Yield decoded event dicts from the teacher channel."""
        r = self._assert_ready()
        channel = _teacher_channel(user_id)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        logger.debug("Subscribed to teacher channel=%s", channel)
        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                try:
                    data = json.loads(raw["data"])
                    yield data
                except json.JSONDecodeError:
                    logger.warning("Received non-JSON message on channel=%s", channel)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            logger.debug("Unsubscribed from teacher channel=%s", channel)


# Singleton instance used across the application
event_bus = EventBus()
