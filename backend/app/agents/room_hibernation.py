"""人類離席/未應答 → 全房休眠（pause-and-hold），回來自動喚醒。

Phase 43（spec 20 §3 / §11.7、spec 16）。兩個觸發匯流成同一個「暫停」狀態：

* **斷線離席**（presence grace 後，``ws/presence_tracker`` on_absent hook）→ ``suspend_room``
* **被點名（cued）逾時仍在線未回應**（``cue_timeout_watcher`` 單人房分支）→ ``suspend_room``

回來喚醒：

* **重連**（presence on_present hook）→ ``resume_room``
* **群組發話**（``ws/chat_ws`` 群發分支）→ ``resume_room``

休眠 ＝ ``Project.status="suspended"``（所有背景 watcher 都 ``WHERE status=="active"``，
自動略過）＋ timer ``pause(reason="awaiting_human")``（凍結時鐘）＋ ``stop_all_agents``
（拆 agent task 省資源）＋ publish ``room_paused``。
喚醒 ＝ 反向：``status="active"`` ＋ timer ``resume``（休眠時長算進 total_paused_seconds）
＋ ``start_all_agents``（重建 agent，同 main.py 重啟復原路徑）＋ publish ``room_resumed``。

優先序（仿 ``app/llm/fail_stop.py``）：``teacher`` / ``llm_down`` 暫停優先——
``suspend_room`` 遇「已暫停」房 no-op（不覆蓋理由）；``resume_room`` 只解凍
``pause_reason=="awaiting_human"`` 房（老師手動 / llm_down 暫停不被自動續跑）。

死鎖防護：本系統每房單一真人、列管老師唯讀不可入座（``projects/access.py``），
故不走「等到上限就丟下人往下走」；改為休眠成靜止資料（無 live loop、被所有 watcher
略過、agent 已拆），回來原地解凍。永不回來＝極省資源的常駐 suspended 列，留待
老師/admin 後台處理或日後 GC。
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import update

from app.db.models.project import Project
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

_PAUSE_REASON = "awaiting_human"
_STATUS_SUSPENDED = "suspended"
_STATUS_ACTIVE = "active"

# 每房一把鎖，序列化 suspend/resume——避免多觸發源並發（presence on_present +
# chat 群發 resume；presence on_absent + cue _hold_and_suspend）造成 TOCTOU
# （重複 start_all_agents 起兩個同席 agent、或重複廣播 room_paused）。
_room_locks: dict[UUID, asyncio.Lock] = {}


def _lock_for(project_id: UUID) -> asyncio.Lock:
    lock = _room_locks.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _room_locks[project_id] = lock
    return lock


async def _set_status(project_id: UUID, status: str) -> None:
    """寫 Project.status（休眠/喚醒只動這一欄；其餘狀態皆 durable，免快照）。"""
    async with async_session_factory() as session:
        await session.execute(
            update(Project).where(Project.id == project_id).values(status=status)
        )
        await session.commit()


async def suspend_room(project_id: UUID) -> None:
    """人類離席/未應答 → 全房休眠。

    已被任何理由暫停（teacher / llm_down / 已 awaiting_human）的房 no-op，
    不覆蓋既有暫停理由。
    """
    from app.events.bus import event_bus
    from app.events.types import RoomPausedEvent
    from app.seats.manager import seat_manager
    from app.timer.service import TimerService

    async with _lock_for(project_id):
        state = await TimerService.get_state(project_id)
        if state is None or state.is_paused():
            return  # 未初始化 / 已暫停 → 不重複暫停、不覆蓋理由

        # 取消任何進行中的 cue 倒數——離席期間不該繼續催/放棄人類。
        try:
            from app.agents.cue_timeout_watcher import cancel_all_cue_watchers

            cancel_all_cue_watchers(project_id)
        except Exception:
            logger.debug(
                "suspend_room cancel cue watchers failed project=%s", project_id,
                exc_info=True,
            )

        await TimerService.pause(project_id, reason=_PAUSE_REASON)
        await _set_status(project_id, _STATUS_SUSPENDED)
        try:
            await seat_manager.stop_all_agents(project_id)
        except Exception:
            logger.exception(
                "suspend_room stop_all_agents failed project=%s", project_id
            )
        await event_bus.publish(
            RoomPausedEvent(project_id=project_id, reason=_PAUSE_REASON)
        )
    logger.info("Room suspended (awaiting human) project=%s", project_id)


async def resume_room(project_id: UUID) -> None:
    """人類回來/發話 → 喚醒。

    只解凍 ``pause_reason=="awaiting_human"`` 的房；未暫停 / 老師手動 / llm_down
    暫停 → no-op（不自動續跑，老師仍握控制權）。
    """
    from app.events.bus import event_bus
    from app.events.types import RoomResumedEvent
    from app.seats.manager import seat_manager
    from app.timer.service import TimerService

    async with _lock_for(project_id):
        state = await TimerService.get_state(project_id)
        if state is None or state.pause_reason != _PAUSE_REASON:
            return  # 未暫停 / 非本模組暫停 → 不自動喚醒

        # 先 resume timer（清 paused_at、把休眠時長計入 total_paused_seconds），
        # 再翻 status=active——避免「status 已 active 但 timer 仍 paused」的中間窗讓
        # progression/timer watcher 看到半喚醒狀態（兩者皆 WHERE status=active）。
        await TimerService.resume(project_id)
        await _set_status(project_id, _STATUS_ACTIVE)

        # Phase 42 補正 R4（裁定⑤）：休眠可超過 round_lock TTL（1 小時）——喚醒時
        # 把本關回合鎖鍵續期，避免 round／參與累積默默歸零。
        try:
            from sqlalchemy import select

            from app.agents import round_lock
            from app.db.models.project import Project
            from app.db.session import async_session_factory

            async with async_session_factory() as session:
                sub_phase = await session.scalar(
                    select(Project.current_sub_phase).where(Project.id == project_id)
                )
            if sub_phase:
                await round_lock.refresh_ttl(project_id, str(sub_phase))
        except Exception:
            logger.debug(
                "resume_room round_lock ttl refresh failed project=%s",
                project_id, exc_info=True,
            )

        try:
            await seat_manager.start_all_agents(project_id)
        except Exception:
            logger.exception(
                "resume_room start_all_agents failed project=%s", project_id
            )
        await event_bus.publish(RoomResumedEvent(project_id=project_id))

        # Phase 42 補正 R4（D5 縫 a）：LLM 判定 down 期間人回來——喚醒照做（人在席
        # 的事實成立），但立即以 llm_down 重新暫停＋banner，不留下「房醒了、agent
        # 全靜默、watcher 樣板強推」的假活狀態（spec 20 §13 fail-stop 初衷）。
        try:
            from app.llm.health_monitor import health_monitor

            if health_monitor.is_down():
                from app.events.types import RoomPausedEvent

                await TimerService.pause(project_id, reason="llm_down")
                await event_bus.publish(
                    RoomPausedEvent(project_id=project_id, reason="llm_down")
                )
                logger.warning(
                    "resume_room during LLM outage → re-paused llm_down project=%s",
                    project_id,
                )
        except Exception:
            logger.exception(
                "resume_room llm_down re-pause failed project=%s", project_id
            )
    logger.info("Room resumed (human returned) project=%s", project_id)
