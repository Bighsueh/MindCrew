"""「你的任務」最新狀態（Phase 42 A3，spec 05 Flow 12 / spec 20 §12.4）。

組長每次發 `set_user_task` action，後端在 publish `user_task` WS 事件的同時把
最新任務寫進 Redis（與 boundary_signal 同模式）。兩個消費者：
1. `human_input_check.confirm_context_active`——confirm 語境白名單的權威來源
   （`action_kind=confirm` 且 sub_phase 相符才生效；任務更換／換關即失效）。
2. （未來）組長 context 注入「目前給使用者的待辦」。

任一時刻至多一個任務（後到覆蓋）；`task_text=None` 視為清除。
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

_TTL_SECONDS = 3600

VALID_ACTION_KINDS = frozenset({"chat", "note", "move", "confirm"})


def _key(project_id: UUID) -> str:
    return f"project:{project_id}:user_task"


async def set_current(
    project_id: UUID,
    *,
    task_text: str | None,
    sub_phase: str,
    action_kind: str,
) -> None:
    """寫入最新任務；task_text=None 清除（best-effort，失敗不擋事件流）。"""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            if task_text is None:
                await r.delete(_key(project_id))
            else:
                payload = json.dumps(
                    {
                        "task_text": task_text,
                        "sub_phase": sub_phase,
                        "action_kind": action_kind,
                    },
                    ensure_ascii=False,
                )
                await r.set(_key(project_id), payload, ex=_TTL_SECONDS)
        finally:
            await r.aclose()
    except Exception:
        logger.debug("user_task_state.set_current failed project=%s", project_id, exc_info=True)


async def get_current(project_id: UUID) -> dict | None:
    """讀最新任務；無任務／讀取失敗 → None。"""
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
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("user_task_state.get_current failed project=%s", project_id, exc_info=True)
        return None
