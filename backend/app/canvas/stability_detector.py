"""Stability detector — Spec 13 §3 動作停滯偵測。

> ⚠️ **Phase 41（2026-06-09）**：原供 `silent_rearrange` 整理格「連續 N 秒無 canvas action
> → 自動推進」之用；沉默模式移除後，`progression/watcher` 不再讀 `check_stability`，收斂格改
> count/supervisor/time-box 推進。本模組的記錄（`record_canvas_action`/`reset`）目前無 advancement
> 讀者，保留供未來重用與向下相容；`check_stability` 暫無生產呼叫點。

State 存在 Redis key `canvas_last_action:{project_id}`，每次 canvas tool 完成寫入。
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)

_KEY_TMPL = "canvas_last_action:{project_id}"


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def record_canvas_action(project_id: UUID) -> None:
    """每次 canvas tool 成功執行後呼叫，更新 last-action 時戳。"""
    r = await _get_redis()
    try:
        await r.set(_KEY_TMPL.format(project_id=project_id), str(time.time()))
    finally:
        await r.aclose()


async def get_seconds_since_last_action(project_id: UUID) -> float:
    """回傳距離最後一次 canvas action 經過的秒數（無紀錄則回 0）。"""
    r = await _get_redis()
    try:
        raw = await r.get(_KEY_TMPL.format(project_id=project_id))
    finally:
        await r.aclose()
    if not raw:
        return 0.0
    try:
        last_ts = float(raw)
    except ValueError:
        return 0.0
    return max(0.0, time.time() - last_ts)


async def check_stability(
    project_id: UUID,
    threshold_seconds: float = 30.0,
) -> bool:
    """是否已達穩定（>= threshold 秒沒動作）。

    若從未記錄過動作則回 False（避免剛進場就誤判穩定）。
    """
    r = await _get_redis()
    try:
        raw = await r.get(_KEY_TMPL.format(project_id=project_id))
    finally:
        await r.aclose()
    if not raw:
        return False
    try:
        last_ts = float(raw)
    except ValueError:
        return False
    return (time.time() - last_ts) >= threshold_seconds


async def reset(project_id: UUID) -> None:
    """重置 last-action 時戳（進入新 silent_rearrange 階段時呼叫）。"""
    r = await _get_redis()
    try:
        await r.set(_KEY_TMPL.format(project_id=project_id), str(time.time()))
    finally:
        await r.aclose()
