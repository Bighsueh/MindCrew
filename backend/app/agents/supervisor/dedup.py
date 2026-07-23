"""Supervisor Trigger Dedup — Spec 16 §6.5.5（Phase 35）.

供 B3a/B3b/B3c/B3_critical 共用：同一 sub_phase 內每個 trigger 只 fire 一次。

設計：
  - Redis key: ``supervisor_fired_triggers:{project_id}:{sub_phase}``（Set 型別，TTL 24h）
  - 寫入：``supervisor/router.py:decide_supervisor_response()`` 在 B fired 分支 return 之前
  - 讀取：``context_buffer.get_current_context()`` 組裝 ctx 時注入 ``_supervisor_fired_triggers``
  - 清空：``TimerService.start_phase()`` 切換 sub_phase 時呼叫 ``reset_fired_triggers(project_id)``

注意：原 ``_b11_already_asked_this_phase`` 旗標機制只有讀取點，從未被寫入過——本模組是第一次
真正讓 supervisor 的 dedup 啟動。
"""

from __future__ import annotations

import logging
from uuid import UUID

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_KEY_TMPL = "supervisor_fired_triggers:{project_id}:{sub_phase}"
_KEY_PREFIX_TMPL = "supervisor_fired_triggers:{project_id}:"
_TTL_SECONDS = 86400  # 24h；防止 stale，避免 abandoned phase 殘留


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_fired_triggers(project_id: UUID, sub_phase: str | None) -> set[str]:
    """讀回該 sub_phase 已 fire 的 trigger id 集合；無資料回空 set。"""
    if not sub_phase:
        return set()
    r = await _get_redis()
    try:
        key = _KEY_TMPL.format(project_id=project_id, sub_phase=sub_phase)
        members = await r.smembers(key)
        return set(members) if members else set()
    except Exception:
        logger.debug("get_fired_triggers failed project=%s sub=%s", project_id, sub_phase, exc_info=True)
        return set()
    finally:
        await r.aclose()


async def mark_trigger_fired(
    project_id: UUID, sub_phase: str | None, trigger_id: str,
) -> None:
    """記錄某 trigger 在當前 sub_phase 已 fire；多次呼叫 idempotent。"""
    if not sub_phase or not trigger_id:
        return
    r = await _get_redis()
    try:
        key = _KEY_TMPL.format(project_id=project_id, sub_phase=sub_phase)
        await r.sadd(key, trigger_id)
        await r.expire(key, _TTL_SECONDS)
    except Exception:
        logger.warning(
            "mark_trigger_fired failed project=%s sub=%s trigger=%s",
            project_id, sub_phase, trigger_id, exc_info=True,
        )
    finally:
        await r.aclose()


async def reset_fired_triggers(
    project_id: UUID, sub_phase: str | None = None,
) -> None:
    """清空 fired triggers；sub_phase=None → 清掉該 project 所有 phase 的記錄。"""
    r = await _get_redis()
    try:
        if sub_phase:
            key = _KEY_TMPL.format(project_id=project_id, sub_phase=sub_phase)
            await r.delete(key)
        else:
            pattern = _KEY_PREFIX_TMPL.format(project_id=project_id) + "*"
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await r.delete(*keys)
                if cursor == 0:
                    break
    except Exception:
        logger.warning(
            "reset_fired_triggers failed project=%s sub=%s",
            project_id, sub_phase, exc_info=True,
        )
    finally:
        await r.aclose()
