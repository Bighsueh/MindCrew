"""Supervisor awaiting-reply lock — Fix #1.

當 Supervisor 點名某 crew 後設一個短期鎖（Redis, TTL=45s）。
鎖期間 Supervisor 不再發話，直到：
  (a) 被點名的 crew 在 recent_chat 中出現新訊息；或
  (b) 鎖逾時自動釋放。

防止 Supervisor 在 crew 還沒回應前連續搶話（截圖看到的 4 連發症狀）。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)

_LOCK_KEY_TMPL = "supervisor_awaiting_reply:{project_id}"
_LOCK_TTL_SECONDS = 45


@dataclass(frozen=True)
class AwaitingReply:
    seat_role: str
    display_name: str
    set_at: float


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def set_awaiting_reply(
    project_id: UUID,
    awaited_seat: str,
    awaited_name: str,
) -> None:
    """設定 awaiting-reply 鎖。"""
    payload = json.dumps({
        "seat_role": awaited_seat,
        "display_name": awaited_name,
        "set_at": time.time(),
    })
    try:
        r = await _get_redis()
        try:
            await r.set(
                _LOCK_KEY_TMPL.format(project_id=project_id),
                payload,
                ex=_LOCK_TTL_SECONDS,
            )
        finally:
            await r.aclose()
        logger.info(
            "Supervisor awaiting reply: project=%s seat=%s name=%s",
            project_id, awaited_seat, awaited_name,
        )
    except Exception:
        logger.debug("set_awaiting_reply failed", exc_info=True)


async def _get_lock(project_id: UUID) -> AwaitingReply | None:
    try:
        r = await _get_redis()
        try:
            raw = await r.get(_LOCK_KEY_TMPL.format(project_id=project_id))
        finally:
            await r.aclose()
        if not raw:
            return None
        data = json.loads(raw)
        return AwaitingReply(
            seat_role=data.get("seat_role", ""),
            display_name=data.get("display_name", ""),
            set_at=float(data.get("set_at", 0)),
        )
    except Exception:
        return None


async def _clear_lock(project_id: UUID) -> None:
    try:
        r = await _get_redis()
        try:
            await r.delete(_LOCK_KEY_TMPL.format(project_id=project_id))
        finally:
            await r.aclose()
    except Exception:
        logger.debug("clear lock failed", exc_info=True)


async def check_awaiting_reply(
    project_id: UUID,
    recent_chat: list[dict],
) -> AwaitingReply | None:
    """檢查 supervisor 是否仍在等待 crew 回覆。

    回傳 AwaitingReply 表示「應該繼續等」；回傳 None 表示「可以發話」。

    清鎖條件：
      - awaited crew 已在 recent_chat 出現新訊息（比對 sender_id / sender）
      - 鎖逾時（由 Redis TTL 自動處理）
    """
    lock = await _get_lock(project_id)
    if lock is None:
        return None

    # 檢查 awaited 是否已回覆：掃 recent_chat 最後 20 則
    awaited_seat_lower = lock.seat_role.lower()
    awaited_name = lock.display_name
    for msg in recent_chat[-20:]:
        sender_id = str(msg.get("sender_id", "")).lower()
        sender_field = str(msg.get("sender", ""))
        # crew 的 agent_id 通常是 "agent_crew_2" 之類，包含 seat_role 子字串
        if awaited_seat_lower and awaited_seat_lower in sender_id:
            await _clear_lock(project_id)
            return None
        if awaited_name and awaited_name in sender_field:
            await _clear_lock(project_id)
            return None

    return lock


def detect_crew_mention(
    content: str,
    seats: list[dict],
) -> tuple[str, str] | None:
    """掃 supervisor 發言內容，找出第一個被點名的 crew。

    回傳 (seat_role, display_name)；沒點名回 None。
    用 display_name（如「陳建宏」）直接子字串比對；@mention 形式也涵蓋。
    """
    if not content or not seats:
        return None
    for seat in seats:
        if seat.get("type") != "ai":
            continue
        role = str(seat.get("role", ""))
        if "supervisor" in role.lower():
            continue
        name = str(seat.get("display_name", "")).strip()
        if not name:
            continue
        if name in content:
            return role, name
    return None
