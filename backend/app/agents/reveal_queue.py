"""Reveal queue — Spec 13 §3 reveal_round 模式的輪序管理。

Redis 結構：
  list `reveal_queue:{project_id}`  含 seat_role 順序
  set  `reveal_done:{project_id}`   已唸完的 seat
  hash `reveal_meta:{project_id}`   {sub_phase: "1.1c", started_at: ts}
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _queue_key(project_id: UUID) -> str:
    return f"reveal_queue:{project_id}"


def _done_key(project_id: UUID) -> str:
    return f"reveal_done:{project_id}"


def _meta_key(project_id: UUID) -> str:
    return f"reveal_meta:{project_id}"


async def start_reveal_round(
    project_id: UUID,
    seat_order: list[str],
    sub_phase_id: str,
) -> None:
    """開始一輪 reveal_round，重置 queue + done。"""
    r = await _get_redis()
    try:
        async with r.pipeline(transaction=True) as pipe:
            await pipe.delete(_queue_key(project_id))
            await pipe.delete(_done_key(project_id))
            await pipe.delete(_meta_key(project_id))
            if seat_order:
                await pipe.rpush(_queue_key(project_id), *seat_order)
            await pipe.hset(_meta_key(project_id), mapping={
                "sub_phase": sub_phase_id,
                "started_at": str(time.time()),
                "total": str(len(seat_order)),
            })
            await pipe.execute()
    finally:
        await r.aclose()
    logger.info(
        "Reveal round started project=%s sub_phase=%s order=%s",
        project_id, sub_phase_id, seat_order,
    )


async def peek_next_seat(project_id: UUID) -> str | None:
    """取得當前該輪到的 seat（不消耗）。"""
    r = await _get_redis()
    try:
        seats = await r.lrange(_queue_key(project_id), 0, 0)
    finally:
        await r.aclose()
    return seats[0] if seats else None


async def advance_reveal(project_id: UUID, seat_role: str) -> bool:
    """seat_role 完成揭示。回傳是否成功推進。"""
    next_seat = await peek_next_seat(project_id)
    if next_seat != seat_role:
        return False

    r = await _get_redis()
    try:
        async with r.pipeline(transaction=True) as pipe:
            await pipe.lpop(_queue_key(project_id))
            await pipe.sadd(_done_key(project_id), seat_role)
            await pipe.execute()
    finally:
        await r.aclose()
    return True


async def get_queue(project_id: UUID) -> list[str]:
    r = await _get_redis()
    try:
        return await r.lrange(_queue_key(project_id), 0, -1)
    finally:
        await r.aclose()


async def is_round_complete(project_id: UUID) -> bool:
    """所有人都唸完。"""
    queue = await get_queue(project_id)
    return len(queue) == 0


async def reset(project_id: UUID) -> None:
    r = await _get_redis()
    try:
        async with r.pipeline(transaction=True) as pipe:
            await pipe.delete(_queue_key(project_id))
            await pipe.delete(_done_key(project_id))
            await pipe.delete(_meta_key(project_id))
            await pipe.execute()
    finally:
        await r.aclose()
