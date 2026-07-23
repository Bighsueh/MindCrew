"""LLM fail-stop 編排 — Phase 42 D5（G14／#35，spec 20 §13.3/§13.4）。

``health_monitor`` 判定 down/up 變化時呼叫本模組，對**所有進行中房間**做可恢復的
全房暫停／自動恢復：

* ``on_llm_down``：未暫停的 active 房 → ``timer_state.pause_reason="llm_down"``＋
  publish ``room_paused``。已暫停房（含老師手動 ``"teacher"``）不碰、不覆蓋。
* ``on_llm_recovered``：只 resume ``pause_reason=="llm_down"`` 房＋publish
  ``room_resumed``。老師手動暫停的房不被自動續跑（§13.4）。

老師通知（spec §13.3.4）依 user 2026-06-14 裁定不做——可視性由 admin
``GET /api/admin/llm-health`` 涵蓋（規格偏離已記於 progress.md）。
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.db.models.project import Project
from app.db.session import async_session_factory
from app.timer.schemas import TimerState

logger = logging.getLogger(__name__)


async def _active_rooms() -> list[tuple]:
    """回 (project_id, timer_state_raw) 清單（status=active）。"""
    async with async_session_factory() as session:
        rows = await session.execute(
            select(Project.id, Project.timer_state).where(Project.status == "active")
        )
        return list(rows.all())


def _state_of(raw) -> TimerState:
    try:
        return TimerState.model_validate(raw or {})
    except Exception:
        return TimerState()


async def on_llm_down() -> None:
    """判定 LLM down：暫停所有未暫停的 active 房（pause_reason=llm_down）。"""
    from app.events.bus import event_bus
    from app.events.types import RoomPausedEvent
    from app.timer.service import TimerService

    paused = 0
    for project_id, raw_state in await _active_rooms():
        try:
            if _state_of(raw_state).is_paused():
                continue  # 老師手動或已 llm_down 暫停 → 不重複暫停、不覆蓋理由
            await TimerService.pause(project_id, reason="llm_down")
            await event_bus.publish(
                RoomPausedEvent(project_id=project_id, reason="llm_down")
            )
            paused += 1
        except Exception:
            logger.exception("fail-stop pause failed project=%s", project_id)
    logger.warning("LLM fail-stop: paused %d room(s)", paused)


async def reconcile_on_startup() -> None:
    """Phase 42 補正 R4（P1-7）：重啟孤兒房收復（spec 20 §13.4 自動恢復）。

    health_monitor 是純 in-memory **邊緣觸發**——outage 期間重啟 backend 會弄丟
    「recovered」邊緣，`pause_reason="llm_down"` 的房永久卡暫停（admin 面板還會
    呈現 overall=up 但 affected_rooms 非空的矛盾）。啟動時先跑一次健檢：
    乾淨（overall=up）→ 補跑 on_llm_recovered 收復孤兒房；有任何失敗訊號 →
    不動（讓背景 monitor 依正常邊緣處理，避免 outage 進行中誤 resume）。
    """
    from app.llm.health_monitor import health_monitor

    try:
        await health_monitor.run_health_check_once()
    except Exception:
        logger.exception("startup health check failed — skip llm_down reconciliation")
        return
    snapshot = health_monitor.snapshot()
    if snapshot.get("overall_status") == "up":
        logger.info("startup reconciliation: LLM healthy → recover llm_down orphans")
        await on_llm_recovered()
    else:
        logger.warning(
            "startup reconciliation: LLM %s → keep llm_down rooms paused",
            snapshot.get("overall_status"),
        )


async def on_llm_recovered() -> None:
    """LLM 恢復：只 resume pause_reason=llm_down 的房；老師手動暫停不動。"""
    from app.events.bus import event_bus
    from app.events.types import RoomResumedEvent
    from app.timer.service import TimerService

    resumed = 0
    for project_id, raw_state in await _active_rooms():
        try:
            if _state_of(raw_state).pause_reason != "llm_down":
                continue  # 未暫停 / 老師手動暫停 → 不自動續跑
            await TimerService.resume(project_id)
            await event_bus.publish(RoomResumedEvent(project_id=project_id))
            resumed += 1
        except Exception:
            logger.exception("fail-stop resume failed project=%s", project_id)
    logger.info("LLM recovery: resumed %d room(s)", resumed)
