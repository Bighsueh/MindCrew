"""組長（supervisor agent）活性追蹤（Phase 42 A1，spec 04-06 §5.8 v4.25）。

watcher 兜底情況 (b)「組長 agent 失能（逾時無動作）」的判定依據：
act.py 在組長每次完成決策（ActEngine.execute 被呼叫）時打一次心跳；
watcher 讀心跳距今超過門檻才認定失能。

保守原則：心跳缺失（如剛重啟、Redis 不可達）一律視為「未失能」——
寧可晚一點由 time-box 兜底，也不誤搶組長的推進權。
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

logger = logging.getLogger(__name__)

# 組長失能門檻：距最後一次成功決策超過此秒數（spec 未量化；
# Phase 42 A1 裁定 180s ≈ 組長決策週期上限的數倍，記錄於 progress.md）。
SUPERVISOR_STALL_SECONDS = 180.0

_TTL_SECONDS = 3600


def _key(project_id: UUID) -> str:
    return f"project:{project_id}:supervisor_last_act_ts"


async def mark_supervisor_active(project_id: UUID) -> None:
    """組長完成一輪決策時打心跳（best-effort）。"""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await r.set(_key(project_id), str(time.time()), ex=_TTL_SECONDS)
        finally:
            await r.aclose()
    except Exception:
        logger.debug(
            "mark_supervisor_active failed project=%s", project_id, exc_info=True
        )


async def supervisor_stalled(
    project_id: UUID, threshold_seconds: float = SUPERVISOR_STALL_SECONDS
) -> bool:
    """組長是否失能（距最後心跳超過門檻）。心跳缺失／讀取失敗 → False（保守）。"""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            raw = await r.get(_key(project_id))
        finally:
            await r.aclose()
        if not raw:
            return False
        return (time.time() - float(raw)) >= threshold_seconds
    except Exception:
        logger.debug(
            "supervisor_stalled check failed project=%s", project_id, exc_info=True
        )
        return False
