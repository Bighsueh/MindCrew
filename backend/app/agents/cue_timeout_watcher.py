"""Phase 28 — Cue Timeout Watcher（per-cue asyncio.Task + retry state machine）。

當 supervisor 透過 set_directive 點名人類席位，act.py 會呼叫
``start_cue_timeout_watcher`` 啟動倒數。倒數結束時：

  - 若已 retry 次數 < ``cue_max_retries`` → publish ``CueTimeoutEvent``
    (will_retry=True)、increment retry counter，等 supervisor B7 reminder
    再次寫 invited_speaker（觸發新一輪 watcher）。
  - 若達 ``cue_max_retries`` → publish ``CueAbandonedEvent``、清空
    invited_speaker、reset retry counter、設 cooldown Redis key TTL=300s。

人類在群組發話 / pass 時，``notify_human_speak_in_group`` / chat_ws pass
handler 會呼叫 ``cancel_cue_timeout_watcher`` 取消正在倒數的 task。

Architecture：per-cue asyncio.Task（不用 polling）—倒數精準到 ms，cancel
直接呼叫 task.cancel()。Module-level dict 追蹤 active tasks。

Limitation：backend restart 後 in-flight task 會消失；spec 不要求跨重啟
durability，stale invited_speaker 由下個 ASSESS tick 自然處理。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from uuid import UUID

from app.config import settings
from app.db.models.seat import SEAT_ROLE_HUMAN_CREATOR

logger = logging.getLogger(__name__)


# (project_id, target_seat_role) → asyncio.Task
_active_watchers: dict[tuple[UUID, str], asyncio.Task[None]] = {}

# Cooldown TTL after abandon — supervisor 在這段期間不該主動再 cue 同一席位。
_COOLDOWN_SECONDS_AFTER_ABANDON = 300

# Retry counter TTL safety margin — 確保 counter 跨越所有 retry cycle 不會過期
# (timeout_seconds * (max_retries + 2))
_RETRY_TTL_MULTIPLIER_OFFSET = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def start_cue_timeout_watcher(
    project_id: UUID,
    target_seat_role: str,
    from_seat_role: str,
    timeout_seconds: int = 180,
    max_retries: int = 5,
) -> None:
    """啟動 cue timeout 倒數。**Idempotent** — 同一 (project, seat) 重複呼叫
    會 cancel 舊 task 再起新的，保持單一 watcher in-flight。

    Args:
        project_id: 專案 ID。
        target_seat_role: 被 cue 的人類席位 seat_role。
        from_seat_role: 點名者（通常是 ``supervisor``）。
        timeout_seconds: 單次 timeout 秒數（預設 180 = 3 分鐘）。
        max_retries: 達此次數後再 timeout 進入 abandoned（預設 5）。
    """
    key = (project_id, target_seat_role)
    # idempotent: 先 cancel 既有 task（避免兩個 task 同時倒數）
    old = _active_watchers.pop(key, None)
    if old is not None and not old.done():
        old.cancel()
    task = asyncio.create_task(
        _watch(project_id, target_seat_role, from_seat_role, timeout_seconds, max_retries)
    )
    _active_watchers[key] = task
    logger.info(
        "cue_timeout_watcher started project=%s seat=%s timeout=%ds max_retries=%d",
        project_id, target_seat_role, timeout_seconds, max_retries,
    )


def cancel_cue_timeout_watcher(
    project_id: UUID, target_seat_role: str
) -> bool:
    """取消 (project, seat) 的 watcher。回傳是否有 task 被 cancel。"""
    key = (project_id, target_seat_role)
    task = _active_watchers.pop(key, None)
    if task is None or task.done():
        return False
    task.cancel()
    logger.info(
        "cue_timeout_watcher cancelled project=%s seat=%s",
        project_id, target_seat_role,
    )
    return True


def has_active_watcher(project_id: UUID, target_seat_role: str) -> bool:
    """Test helper：檢查指定 (project, seat) 是否有 active watcher。"""
    task = _active_watchers.get((project_id, target_seat_role))
    return task is not None and not task.done()


def cancel_all_cue_watchers(project_id: UUID) -> int:
    """取消某 project 所有 in-flight cue watcher，回傳取消數。

    Phase 43：人類離席 → 全房休眠時呼叫，避免 watcher 在離席期間繼續倒數/放棄。
    """
    cancelled = 0
    for key in list(_active_watchers.keys()):
        if key[0] != project_id:
            continue
        task = _active_watchers.pop(key, None)
        if task is not None and not task.done():
            task.cancel()
            cancelled += 1
    if cancelled:
        logger.info(
            "cue_timeout_watcher cancelled %d watcher(s) project=%s",
            cancelled, project_id,
        )
    return cancelled


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


async def _watch(
    project_id: UUID,
    target_seat_role: str,
    from_seat_role: str,
    timeout_seconds: int,
    max_retries: int,
) -> None:
    start_ts = time.time()
    try:
        await asyncio.sleep(timeout_seconds)
    except asyncio.CancelledError:
        return
    finally:
        # 倒數完成（不論是否 cancelled）從 registry 移除自己
        _active_watchers.pop((project_id, target_seat_role), None)

    try:
        await _handle_timeout(
            project_id=project_id,
            target_seat_role=target_seat_role,
            from_seat_role=from_seat_role,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            start_ts=start_ts,
        )
    except Exception:
        logger.exception(
            "cue_timeout_watcher _handle_timeout failed project=%s seat=%s",
            project_id, target_seat_role,
        )


async def _handle_timeout(
    *,
    project_id: UUID,
    target_seat_role: str,
    from_seat_role: str,
    timeout_seconds: int,
    max_retries: int,
    start_ts: float,
) -> None:
    """倒數結束後決定：人類席 → 等待休眠（Phase 43）；其餘 → retry / abandon。"""
    # 解析席位顯示名（hold/reminder/pivot 訊息會 @ 它）
    from app.agents.cue_chat_messages import (
        publish_pivot_chat,
        publish_reminder_chat,
        resolve_seat_display_name,
    )
    human_name = await resolve_seat_display_name(project_id, target_seat_role)

    # Phase 43（spec 20 §3/§11.7）：cue watcher 僅對人類席啟動（act.py），故
    # target=人類專屬席＝唯一真人未應答 → 不放棄、不「先繼續往下走」，改貼
    # 「在這裡等你」+ 全房休眠（pause timer + 停 agent + status=suspended），保留
    # invited_speaker、不重啟倒數（改等人發話自動喚醒，見 room_hibernation）。
    if target_seat_role == SEAT_ROLE_HUMAN_CREATOR:
        await _hold_and_suspend(
            project_id=project_id,
            from_seat_role=from_seat_role,
            human_name=human_name,
        )
        return

    retry_count = await _get_retry_count(project_id, target_seat_role)

    if retry_count < max_retries:
        # 還能 retry：publish timeout event、增加 retry counter，
        # publish reminder chat message（模板化，未來可升級 LLM-generated），
        # 重新寫入 invited_speaker → 新一輪 cue 起跑（watcher 由 act.py 重啟）。
        await _set_retry_count(
            project_id, target_seat_role,
            retry_count + 1,
            ttl_seconds=timeout_seconds * (max_retries + _RETRY_TTL_MULTIPLIER_OFFSET),
        )
        await _publish_timeout_event(
            project_id=project_id,
            target_seat_role=target_seat_role,
            from_seat_role=from_seat_role,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            max_retries=max_retries,
            will_retry=True,
        )
        # B7：supervisor reminder（模板化）
        await publish_reminder_chat(
            project_id=project_id,
            from_seat_role=from_seat_role,
            human_name=human_name,
            retry_count=retry_count,
            max_retries=max_retries,
            elapsed_minutes=int(timeout_seconds * (retry_count + 1) / 60),
        )
        # B7：重寫 invited_speaker（保持 cue 狀態）+ 重啟 watcher
        await _rewrite_invited_speaker_and_restart(
            project_id=project_id,
            target_seat_role=target_seat_role,
            from_seat_role=from_seat_role,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        logger.info(
            "cue_timeout retry %d/%d project=%s seat=%s",
            retry_count + 1, max_retries, project_id, target_seat_role,
        )
        return

    # 達 retry 上限 → abandon
    await _publish_timeout_event(
        project_id=project_id,
        target_seat_role=target_seat_role,
        from_seat_role=from_seat_role,
        timeout_seconds=timeout_seconds,
        retry_count=retry_count,
        max_retries=max_retries,
        will_retry=False,
    )
    await _clear_invited_speaker(project_id, from_seat_role)
    await _reset_retry_counter(project_id, target_seat_role)
    await _set_cooldown(project_id, target_seat_role, _COOLDOWN_SECONDS_AFTER_ABANDON)
    await _publish_abandoned_event(
        project_id=project_id,
        target_seat_role=target_seat_role,
        from_seat_role=from_seat_role,
        total_attempts=max_retries + 1,
        elapsed_seconds=int(time.time() - start_ts),
        cooldown_seconds=_COOLDOWN_SECONDS_AFTER_ABANDON,
    )
    # B7：supervisor pivot 訊息（模板化）
    await publish_pivot_chat(
        project_id=project_id,
        from_seat_role=from_seat_role,
        human_name=human_name,
        total_attempts=max_retries + 1,
    )
    logger.info(
        "cue abandoned project=%s seat=%s total_attempts=%d",
        project_id, target_seat_role, max_retries + 1,
    )


async def _hold_and_suspend(
    *,
    project_id: UUID,
    from_seat_role: str,
    human_name: str,
) -> None:
    """Phase 43：單人房 cue 逾時 → supervisor 貼「在這裡等你」+ 全房休眠等人回應。

    先貼訊息（event_bus 獨立於 agent loop，休眠停 agent 後訊息仍送達），再休眠。
    invited_speaker 保留不清、retry counter 不增——人發話即由 room_hibernation 喚醒。
    """
    from app.agents.cue_chat_messages import publish_awaiting_hold_chat
    from app.agents.room_hibernation import suspend_room

    await publish_awaiting_hold_chat(
        project_id=project_id,
        from_seat_role=from_seat_role,
        human_name=human_name,
    )
    await suspend_room(project_id)
    logger.info("cue hold+suspend project=%s (awaiting human)", project_id)


# ---------------------------------------------------------------------------
# Redis helpers — retry counter / cooldown key
# ---------------------------------------------------------------------------


def _cue_cooldown_key(project_id: UUID, seat_role: str) -> str:
    return f"project:{project_id}:cue_cooldown:{seat_role}"


async def _get_redis() -> Any:
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _get_retry_count(project_id: UUID, seat_role: str) -> int:
    """讀 Redis cue_retry counter。不存在回 0。"""
    from app.agents.turn_controller import _cue_retry_key

    try:
        r = await _get_redis()
        try:
            value = await r.get(_cue_retry_key(project_id, seat_role))
        finally:
            await r.aclose()
        return int(value) if value else 0
    except Exception:
        logger.debug("_get_retry_count failed", exc_info=True)
        return 0


async def _set_retry_count(
    project_id: UUID, seat_role: str, count: int, ttl_seconds: int
) -> None:
    from app.agents.turn_controller import _cue_retry_key

    try:
        r = await _get_redis()
        try:
            await r.set(
                _cue_retry_key(project_id, seat_role),
                str(count),
                ex=max(ttl_seconds, 60),  # 最少 60 秒，避免 TTL 太短
            )
        finally:
            await r.aclose()
    except Exception:
        logger.debug("_set_retry_count failed", exc_info=True)


async def _reset_retry_counter(project_id: UUID, seat_role: str) -> None:
    from app.agents.turn_controller import reset_cue_retry

    await reset_cue_retry(project_id, seat_role)


async def _set_cooldown(project_id: UUID, seat_role: str, ttl_seconds: int) -> None:
    try:
        r = await _get_redis()
        try:
            await r.set(
                _cue_cooldown_key(project_id, seat_role),
                "1",
                ex=ttl_seconds,
            )
        finally:
            await r.aclose()
    except Exception:
        logger.debug("_set_cooldown failed", exc_info=True)


# ---------------------------------------------------------------------------
# Blackboard helper — clear invited_speaker on abandon
# ---------------------------------------------------------------------------


async def _clear_invited_speaker(project_id: UUID, from_seat_role: str) -> None:
    """abandon 時清空 invited_speaker，保留其他 directive 欄位。"""
    try:
        from app.agents.blackboard import BlackboardManager
        from app.agents.blackboard_schemas import CoordinationDirective

        bb = BlackboardManager(
            project_id=project_id,
            agent_id=from_seat_role,
            seat_role=from_seat_role,
        )
        existing = await bb.read_coordination_directive()
        if existing is None:
            return
        cleared = CoordinationDirective(
            round_type=existing.round_type,
            focus_topic=existing.focus_topic,
            invited_speaker=None,
            instruction=existing.instruction,
        )
        await bb.write_coordination_directive(cleared)
    except Exception:
        logger.debug("_clear_invited_speaker failed", exc_info=True)


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------


async def _publish_timeout_event(
    *,
    project_id: UUID,
    target_seat_role: str,
    from_seat_role: str,
    timeout_seconds: int,
    retry_count: int,
    max_retries: int,
    will_retry: bool,
) -> None:
    try:
        from app.events.bus import event_bus
        from app.events.types import CueTimeoutEvent

        await event_bus.publish(
            CueTimeoutEvent(
                project_id=project_id,
                target_seat_role=target_seat_role,
                from_seat_role=from_seat_role,
                timeout_seconds=timeout_seconds,
                retry_count=retry_count,
                max_retries=max_retries,
                will_retry=will_retry,
            )
        )
    except Exception:
        logger.debug("_publish_timeout_event failed", exc_info=True)


async def _publish_abandoned_event(
    *,
    project_id: UUID,
    target_seat_role: str,
    from_seat_role: str,
    total_attempts: int,
    elapsed_seconds: int,
    cooldown_seconds: int,
) -> None:
    try:
        from app.events.bus import event_bus
        from app.events.types import CueAbandonedEvent

        await event_bus.publish(
            CueAbandonedEvent(
                project_id=project_id,
                target_seat_role=target_seat_role,
                from_seat_role=from_seat_role,
                total_attempts=total_attempts,
                elapsed_seconds=elapsed_seconds,
                cooldown_seconds=cooldown_seconds,
            )
        )
    except Exception:
        logger.debug("_publish_abandoned_event failed", exc_info=True)


# ---------------------------------------------------------------------------
# B7：Retry restart helper（reminder/pivot 訊息見 cue_chat_messages.py）
# ---------------------------------------------------------------------------


async def _rewrite_invited_speaker_and_restart(
    *,
    project_id: UUID,
    target_seat_role: str,
    from_seat_role: str,
    timeout_seconds: int,
    max_retries: int,
) -> None:
    """retry cycle：重寫 invited_speaker + 重啟 watcher 進入下一輪倒數。"""
    try:
        from app.agents.blackboard import BlackboardManager
        from app.agents.blackboard_schemas import CoordinationDirective

        bb = BlackboardManager(
            project_id=project_id,
            agent_id=from_seat_role,
            seat_role=from_seat_role,
        )
        existing = await bb.read_coordination_directive()
        directive = CoordinationDirective(
            round_type=existing.round_type if existing else "respond_to",
            focus_topic=existing.focus_topic if existing else None,
            invited_speaker=target_seat_role,
            instruction=existing.instruction if existing else "",
        )
        await bb.write_coordination_directive(directive)
        await start_cue_timeout_watcher(
            project_id=project_id,
            target_seat_role=target_seat_role,
            from_seat_role=from_seat_role,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    except Exception:
        logger.debug("_rewrite_invited_speaker_and_restart failed", exc_info=True)
