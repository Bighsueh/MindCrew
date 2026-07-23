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
            now = str(time.time())
            await pipe.hset(_meta_key(project_id), mapping={
                "sub_phase": sub_phase_id,
                "started_at": now,
                # head_since：當前隊首成為隊首的時間，供 round_robin 人類逾時 pass 判斷。
                "head_since": now,
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


# 原子推進：只在 seat_role 仍為隊首時 pop。peek+pop 分兩段時，多個 agent
# 並行呼叫（is_my_turn 每 tick 都會觸發 timeout 推進）會 double-pop 跳過下一
# 席位（觀察到 crew_2 永遠被跳過）。用 Lua 保證「比對隊首→pop→記 done→更新
# head_since」整段原子。
_ADVANCE_LUA = """
local head = redis.call('LINDEX', KEYS[1], 0)
if head == ARGV[1] then
  redis.call('LPOP', KEYS[1])
  redis.call('SADD', KEYS[2], ARGV[1])
  redis.call('HSET', KEYS[3], 'head_since', ARGV[2])
  return 1
end
return 0
"""


async def advance_reveal(project_id: UUID, seat_role: str) -> bool:
    """seat_role 完成揭示 → 原子推進。只在 seat_role 仍為隊首時成功（回 True）。"""
    r = await _get_redis()
    try:
        moved = await r.eval(
            _ADVANCE_LUA,
            3,
            _queue_key(project_id),
            _done_key(project_id),
            _meta_key(project_id),
            seat_role,
            str(time.time()),
        )
    finally:
        await r.aclose()
    return bool(moved)


async def seconds_since_head(project_id: UUID) -> float | None:
    """當前隊首成為隊首後經過的秒數；無 meta 時回 None。"""
    r = await _get_redis()
    try:
        raw = await r.hget(_meta_key(project_id), "head_since")
    finally:
        await r.aclose()
    if raw is None:
        return None
    try:
        return time.time() - float(raw)
    except (TypeError, ValueError):
        return None


async def timeout_advance_human_head(
    project_id: UUID,
    human_seats: set[str],
    timeout_s: float,
) -> bool:
    """spec 20 §3.6：round_robin 隊首為人類且逾時 → 視為單次 pass 自動推進。

    回傳是否真的推進。非人類隊首 / 未逾時 / 隊列空 → False（no-op）。
    """
    head = await peek_next_seat(project_id)
    if head is None or head not in human_seats:
        return False
    elapsed = await seconds_since_head(project_id)
    if elapsed is None or elapsed < timeout_s:
        return False
    advanced = await advance_reveal(project_id, head)
    if advanced:
        logger.info(
            "Reveal round: human head %s timed out after %.1fs → auto-pass project=%s",
            head, elapsed, project_id,
        )
    return advanced


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
