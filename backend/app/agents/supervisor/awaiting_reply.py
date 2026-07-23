"""Supervisor awaiting-reply lock — Fix #1.

當 Supervisor 點名某 crew/人類後設一個短期鎖（Redis）。
鎖期間 Supervisor 不再發話，直到：
  (a) 被點名者在 recent_chat 中出現新訊息（被動掃描）／或人類在群組 chat 發話
      （`clear_awaiting_if_seat` 主動清，由 chat_ws 觸發）；或
  (b) 鎖逾時自動釋放。

防止 Supervisor 在對方還沒回應前連續搶話。

**TTL 必須大於 Supervisor 的實際決策週期**，否則鎖永遠在下個決策週期到來前過期、
形同虛設（2026-06 暖場實機：TTL=45s < cadence ~57-60s〔throttle max_interval 45s +
LLM 生成延遲〕→ 組長對著還沒開口的學員連環催 5 次）。故 TTL 取 120s（> 60s cadence
留足餘裕，並涵蓋 LLM 延遲尖峰）。
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
# 必須 > Supervisor 決策週期（throttle max_interval 45s + LLM 延遲 ~15s ≈ 60s），
# 否則鎖在下個週期前過期、無法抑制連發。見模組 docstring。
_LOCK_TTL_SECONDS = 120


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


async def clear_awaiting_if_seat(project_id: UUID, seat_role: str) -> bool:
    """主動清鎖：當 ``seat_role`` 正是 supervisor 在等的對象時清掉鎖並回 True。

    由 chat_ws 在人類於群組 chat 發話時呼叫——拉長 TTL 後，靠這個 hook 讓「人一回話
    supervisor 就能在下個 tick 立刻接話」，不必等到被動掃描或 TTL 過期。
    只在等的對象就是發話者時才清（避免清掉在等別人的鎖）。
    """
    if not seat_role:
        return False
    lock = await _get_lock(project_id)
    if lock is None:
        return False
    if lock.seat_role and lock.seat_role.lower() == seat_role.lower():
        await _clear_lock(project_id)
        logger.info(
            "Supervisor awaiting-reply cleared (human spoke): project=%s seat=%s",
            project_id, seat_role,
        )
        return True
    return False


async def clear_awaiting_any(project_id: UUID) -> bool:
    """無條件清掉 awaiting-reply 鎖（不論鎖在誰身上）。回 True＝原本有鎖。

    由 chat_ws 在**人類於群組 chat 發話**時呼叫。`clear_awaiting_if_seat` 只在「鎖的對象
    ＝發話者本人」時清，當組長 @ 點名的是 *crew*（非人類）時，人類再怎麼發話都清不掉那個
    鎖 → 組長乾等被點名 crew 最久 120s（TTL）＝死房。但「人類主動參與」永遠是更高優先的
    訊號：人一講話組長就該轉而回應人類，不該繼續晾著等某個 crew。故人類群組發話一律清鎖。
    """
    lock = await _get_lock(project_id)
    if lock is None:
        return False
    await _clear_lock(project_id)
    logger.info(
        "Supervisor awaiting-reply cleared (human group speech, was awaiting %s): project=%s",
        lock.seat_role, project_id,
    )
    return True


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
    """掃 supervisor 發言內容，找出第一個被點名的成員席位。

    回傳 (seat_role, name)；沒點名回 None。
    用 name（display_name → user_name → agent_id fallback）直接子字串比對；
    @mention 形式也涵蓋。

    Phase 28 行為調整：原本只命中 AI crew，現在也涵蓋人類席位——
    supervisor 點名學生後同樣設 awaiting-reply lock，讓 supervisor 暫停發話
    等對方回應。Supervisor 自己仍不會被命中（避免自我點名死循環）。
    """
    if not content or not seats:
        return None
    for seat in seats:
        role = str(seat.get("role", ""))
        if "supervisor" in role.lower():
            continue
        name = str(
            seat.get("display_name")
            or seat.get("user_name")
            or seat.get("agent_id")
            or ""
        ).strip()
        if not name:
            continue
        if name in content:
            return role, name
    return None
