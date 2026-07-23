"""Evaluator → 組長的邊界評估訊號（Phase 42 A1，spec 04-06 §5.8 v4.25）。

Evaluator 不再靜默跨 micro/macro 邊界，改把「邊界判定結果」寫進 Redis；
context_buffer 讀出後併入組長的「本關訊號」面板，由組長宣布推進。

key 帶 micro_phase 與 sub_phase，換關後舊訊號自動失效（讀取時比對）。
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

_TTL_SECONDS = 600  # 評估每 20-45s 一輪；10 分鐘沒更新就視為過期


def _key(project_id: UUID) -> str:
    return f"project:{project_id}:boundary_signal"


async def set_boundary_signal(
    project_id: UUID,
    *,
    micro_phase: str | None,
    sub_phase: str | None,
    ready: bool,
    passed: bool,
    total_score: float,
    weak_areas: list[str],
) -> None:
    """寫入最新一輪評估的邊界訊號（best-effort，失敗不擋評估流程）。"""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        payload = json.dumps({
            "micro_phase": micro_phase,
            "sub_phase": sub_phase,
            "ready": ready,
            "passed": passed,
            "total_score": total_score,
            "weak_areas": weak_areas[:5],
        }, ensure_ascii=False)
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await r.set(_key(project_id), payload, ex=_TTL_SECONDS)
        finally:
            await r.aclose()
    except Exception:
        logger.debug("set_boundary_signal failed project=%s", project_id, exc_info=True)


async def get_boundary_signal(
    project_id: UUID,
    current_micro_phase: str | None,
    current_sub_phase: str | None = None,
) -> dict | None:
    """讀出邊界訊號；micro 或 sub 已換關（或無訊號）回 None。

    sub_phase 比對防「上一格的『還不夠』殘影」誤導組長（評估每 20-45s 才更新一輪）。
    """
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            raw = await r.get(_key(project_id))
        finally:
            await r.aclose()
        if not raw:
            return None
        data = json.loads(raw)
        if current_micro_phase and data.get("micro_phase") != current_micro_phase:
            return None
        if current_sub_phase and data.get("sub_phase") != current_sub_phase:
            return None
        return data
    except Exception:
        logger.debug("get_boundary_signal failed project=%s", project_id, exc_info=True)
        return None
