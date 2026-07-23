"""Progression watcher — 兜底推進（Spec 04-06 §5.8 v4.25，Phase 42 A1）。

v4.25 起常態推進權在**組長**（讀「本關訊號」面板 → 宣布 → act `advance_sub_phase`，
見 agents/act_progression.py）。watcher 降級為兜底，每 ~10 秒掃 active 專案，
只在兩種情況代推（含 micro/macro 邊界，經 advance_router 三層路由）：

  (a) time-box 100% 到、且組長未在寬限期（_TIMEBOX_GRACE_SECONDS）內完成
      誠實收尾推進 → 樣板強推（skip gate——時間到＝最終覆蓋，§4.2）。
  (b) 組長 agent 失能（決策迴圈心跳逾時，supervisor_activity）且本格訊號已
      達成 → 代推（gate 照常檢查）。

floor_pct（30–50% 時間下限）與 v4.17/v4.18 無引導者 60% 提前放行閥、教師房
超時升級提醒＋hold——全部移除（時間=上限不設下限；time-box 一體適用，教師
改用 pause/extend）。每次兜底推進都**決定性發一條樣板聊天交代**並持久化
（教學透明，Spec 27 §12.8/§12.10；樣板字串只允許出現在本兜底路徑，04-03 §3.0.2）。

暖場（macro=warmup，Phase 42 B1，spec 28 §5.4）：退場常態＝組長三情境收尾；
watcher 僅在「硬上限 5 分到 **且** 組長失能」時樣板強推（雙條件，與一般格的
time-box＋寬限單條件不同）。由 main.py lifespan 啟動；沒有 timer（used_pct
不可得）時不推進——等教師啟用計時器。
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.db.session import async_session_factory
from app.stages.sub_phases import SUB_PHASES, SubPhase, is_hard_gate

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 10.0
_TIME_BOX_PCT = 100.0
# time-box 100% 後留給組長「誠實收尾再推進」的寬限秒數；寬限內組長健在就不代推。
# （spec 未量化；Phase 42 A1 裁定 90s ≈ 組長一輪 LLM 來回＋watcher 輪詢餘裕，記錄於 progress.md。）
_TIMEBOX_GRACE_SECONDS = 90.0
_SHUTDOWN = False


async def progression_watcher_loop() -> None:
    global _SHUTDOWN
    _SHUTDOWN = False
    logger.info("progression_watcher started (poll=%ds)", int(_POLL_INTERVAL_SECONDS))
    while not _SHUTDOWN:
        try:
            await _tick()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("progression_watcher tick failed")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    logger.info("progression_watcher stopped")


async def stop_progression_watcher() -> None:
    global _SHUTDOWN
    _SHUTDOWN = True


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _gates_pass(project_id: UUID, sub_phase: str) -> bool:
    """Dry-run 兩道 advance gate（deliverables + artifact），全過才 ready。

    與 ``stage_advancement.advance_sub_phase`` 同調，所以 ready 後真正 advance
    不會被 gate 反打。任一檢查拋錯時保守視為「未過」（不貿然推進硬格）。
    """
    try:
        from app.stages.deliverables import check_deliverables

        if not (await check_deliverables(project_id, sub_phase)).passed:
            return False
    except Exception:
        logger.debug("deliverable dry-run failed sub=%s", sub_phase, exc_info=True)
        return False
    try:
        from app.canvas.artifact_gate import check_artifact_gate

        if not (await check_artifact_gate(project_id, sub_phase)).passed:
            return False
    except Exception:
        logger.debug("artifact gate dry-run failed sub=%s", sub_phase, exc_info=True)
        return False
    return True


# Phase 42 B1（spec 28 v2.0 §5.1）：舊「真人 ≥15 字＋45s 放行」暖場參與模型整組移除
# （_HUMAN_PARTICIPATION_SUB_PHASES / _human_participated_in_warmup / _warmup_human_ready
# 等）。真人實質檢核由 round_lock + human_input_check（A2）承擔；暖場退場公式
# 與全員參與判定統一在 progression/warmup_exit.py。


async def _is_ready(project_id: UUID, sp: SubPhase) -> bool:
    if is_hard_gate(sp):
        # Phase 42 D1d (G01)：硬格的真人硬閘——房內有真人且本回合真人尚未完成有效參與時，
        # stall-backstop 不嘗試推進（否則 execute_advance_target 會擋、每 10s 空轉一次 blocked）。
        # time-box 逃生走 used_pct≥100 的 skip_gate_check 路徑，不經此（spec 20 §11.7 防死鎖）。
        try:
            from app.progression.advance_router import human_gate_blocks

            blocked, _ = await human_gate_blocks(project_id, sp.id)
            if blocked:
                return False
        except Exception:
            # 真人閘狀態未知（理論上不會——human_gate_blocks 內部已吞例外）：保守回
            # 「未 ready」，stall-backstop 不嘗試推進（time-box 逃生另走 skip_gate_check
            # 路徑、不靠 _is_ready，故不致死鎖）。
            logger.debug("human gate check in _is_ready failed sub=%s", sp.id, exc_info=True)
            return False
        return await _gates_pass(project_id, sp.id)
    # Phase 41：移除 silent_rearrange「白板靜止才 ready」分支（沉默模式已取消）。
    # 無硬 gate 的軟格恆 ready——常態節奏由組長判斷（Phase 42 A1）；watcher 只在
    # 兜底情況（組長失能/time-box）用到本判定。
    return True


async def _get_used_pct(project_id: UUID) -> float | None:
    try:
        from app.timer.service import TimerService

        return await TimerService.get_used_pct(project_id)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# core
# ---------------------------------------------------------------------------

async def _tick() -> None:
    from app.db.models.project import Project

    async with async_session_factory() as session:
        rows = await session.execute(
            select(Project).where(Project.status == "active")
        )
        projects = rows.scalars().all()

    for p in projects:
        try:
            await _check_one(p.id, p.current_sub_phase, p.current_stage)
        except Exception:
            logger.debug("progression check project=%s failed", p.id, exc_info=True)
        # Phase 42 C0（spec 10 v2.0 §4.7，裁定 6）：move-delta 事件單一消費點。
        try:
            from app.canvas.move_ingest import ingest_moves

            await ingest_moves(p.id)
        except Exception:
            logger.debug("move ingest project=%s failed", p.id, exc_info=True)


async def _check_one(
    project_id: UUID,
    current_sub_phase: str | None,
    current_stage: str | None = None,
) -> None:
    """兜底決策（Phase 42 A1）：只在 (a) time-box＋寬限逾時 (b) 組長失能＋訊號達成 代推。"""
    if not current_sub_phase:
        return
    # 第一鑽石已完成的專案（stage=completed、sub_phase 停在末格）不再有可推之處——
    # 不跳過會在 time-box 永久 100% 下每 tick 觸發 CAS noop 重試（live 2026-06-11 抓到）。
    if current_stage == "completed":
        return
    sp = SUB_PHASES.get(current_sub_phase)
    if sp is None:
        return
    # Phase 42 D5 (G14, spec 20 §13.3)：暫停中房間（LLM fail-stop 或老師手動）不兜底
    # 推進——與 timer watcher 一致（timer/watcher.py is_paused 早退）。
    try:
        from app.timer.service import TimerService

        state = await TimerService.get_state(project_id)
        if state is not None and state.is_paused():
            return
    except Exception:
        logger.debug("pause check failed project=%s", project_id, exc_info=True)
    # 暖場兜底（Phase 42 B1，spec 28 §5.4 / 16 §4.4）：退場常態＝組長三情境收尾，
    # watcher 只在「硬上限 5 分到 **且** 組長失能」時樣板強推（雙條件——硬上限到
    # 而組長健在＝情境 3 坦白收尾，是組長的事，不代推）。
    if sp.macro_stage == "warmup":
        used_pct = await _get_used_pct(project_id)
        if used_pct is None or used_pct < _TIME_BOX_PCT:
            return
        from app.progression.supervisor_activity import supervisor_stalled

        if not await supervisor_stalled(project_id):
            return
        logger.info(
            "warmup backstop：暖場未達標（time-box 放行）project=%s（組長失能）",
            project_id,
        )
        await _advance(
            project_id, current_sub_phase, reason="warmup_time_box",
            skip_gate_check=True,
        )
        return

    used_pct = await _get_used_pct(project_id)
    if used_pct is None:
        return  # 尚無 timer（等教師啟用）→ 不推進

    from app.progression.supervisor_activity import supervisor_stalled

    if used_pct < _TIME_BOX_PCT:
        # 兜底情況 (b)：組長決策迴圈失能、而本格訊號已達成 → 代推（gate 照常）。
        # 組長健在時 watcher 完全不動——常態推進是組長的事（訊號達成即可推，無時間下限）。
        if await supervisor_stalled(project_id) and await _is_ready(project_id, sp):
            await _advance(project_id, current_sub_phase, reason="supervisor_stall")
        return

    # 兜底情況 (a)：time-box 100% 到。先給組長一段寬限做「誠實收尾再推進」；
    # 寬限內組長健在就不代推，寬限過了（或組長已失能）→ 樣板強推，gate 不擋
    # （時間到＝最終覆蓋，spec 04-06 §4.2；防 2026-06-08 盲測 1.1b 死鎖重演）。
    if not await supervisor_stalled(project_id):
        overtime = await _overtime_seconds(project_id, current_sub_phase)
        # 預算讀不到（None）時保守不代推：組長健在會自己收尾；若組長之後
        # 失能則走上面的 stalled 分支，不會因 timer 讀取抖動誤觸 skip-gate 強推。
        if overtime is None or overtime < _TIMEBOX_GRACE_SECONDS:
            return
    await _advance(
        project_id, current_sub_phase, reason="time_box", skip_gate_check=True,
    )


async def _overtime_seconds(
    project_id: UUID, sub_phase: str
) -> float | None:
    """超過 time-box 的**絕對秒數**（used_pct 已 ≥100 時呼叫）；預算/用時不可得回 None。

    ⚠️ 不可用 used_pct 反推（Phase 42 D1d Bug②）：``TimerService.get_used_pct`` 在
    200% 封頂（service.py），用 ``(used_pct-100)/100*budget`` 反推時 overtime 最多
    ＝budget。短格（budget < ``_TIMEBOX_GRACE_SECONDS``，如 2.7=60s／2.5=60s）的
    overtime 被天花板鎖死、永遠到不了寬限 → 巨觀 time-box 逃生（define→completed）
    不可達、2.7 永遠 thrash（live 2026-06-15 坐實）。改讀**未封頂的絕對 used 秒數**。
    """
    try:
        from app.timer.calculator import get_phase_budget_seconds
        from app.timer.service import TimerService

        config = await TimerService.get_config(project_id)
        budget = get_phase_budget_seconds(config, sub_phase)
        if not budget:
            return None
        used = await TimerService.get_used_seconds(project_id)
        if used is None:
            return None
        return max(0.0, float(used) - float(budget))
    except Exception:
        logger.debug("overtime seconds failed project=%s", project_id, exc_info=True)
        return None


async def _advance(
    project_id: UUID,
    from_id: str,
    reason: str,
    skip_gate_check: bool = False,
) -> None:
    """兜底代推：經三層路由執行（含 micro/macro 邊界），成功才發樣板交代。

    先重讀 DB 鮮值：_tick 的快照可能落後 ~10s，組長若已自行推進就不代推
    （advancement 函式另有 CAS guard 作最後防線——雙保險防雙寫跳格）。
    """
    from app.db.models.project import Project

    async with async_session_factory() as session:
        row = await session.execute(
            select(Project.current_sub_phase).where(Project.id == project_id)
        )
        fresh = row.scalar_one_or_none()
    if fresh != from_id:
        logger.debug(
            "backstop skip：sub_phase 已變 project=%s snapshot=%s fresh=%s",
            project_id, from_id, fresh,
        )
        return

    from app.progression.advance_router import (
        execute_advance_target,
        resolve_advance_target,
    )

    target = resolve_advance_target(from_id)
    if target.kind == "none":
        return  # 已是終局（completed）或未知格 → 不動
    result = await execute_advance_target(
        project_id=project_id,
        agent_id="system_progression",
        target=target,
        skip_gate_check=skip_gate_check,
        announce=False,  # 轉場交代由下面的兜底樣板統一負責（04-03 §3.0.2）
    )
    logger.info(
        "progression backstop advance project=%s from=%s kind=%s reason=%s result=%s",
        project_id, from_id, target.kind, reason, result,
    )
    advanced = isinstance(result, str) and (
        result.startswith("sub_advanced")
        or result.startswith("micro_advanced")
        or result.startswith("advanced_to_")
    )
    if advanced:
        to_id = _target_to_sub(target)
        await _announce_transition(project_id, from_id, to_id, reason)


def _target_to_sub(target) -> str | None:
    """解析推進後落點的 sub_phase id（樣板交代用；解析不到回 None）。"""
    if target.kind == "sub":
        return target.to_sub_phase
    if target.kind == "micro":
        from app.stages.sub_phases import get_first_sub_phase_of_micro

        return get_first_sub_phase_of_micro(target.to_micro or "")
    if target.kind == "stage":
        from app.agents.stage_advancement import get_next_stage
        from app.stages.sub_phases import get_first_sub_phase_of_macro

        nxt = get_next_stage(target.from_stage or "")
        if nxt and nxt != "completed":
            return get_first_sub_phase_of_macro(nxt)
    return None


async def _say(project_id: UUID, body: str, stage: str) -> None:
    """白話交代：同時 WS 廣播（即時）+ 寫入 message 表（chat 歷史可追溯）。

    沿用 act.py 的「publish ChatMessageEvent + 寫 Message」雙寫模式，讓教學透明
    不依賴 LLM 自願、也不只是 ephemeral 廣播（修 Spec 27 §12.8/§12.10 的無強制缺口）。
    """
    try:
        from app.events.types import ChatMessageEvent
        from app.events.bus import event_bus
        from app.chinese.converter import chinese_converter
        from app.db.models.message import Message
        from app.agents.personas.display import resolve_display_name

        content = chinese_converter.convert(body)
        sender_name = resolve_display_name("supervisor")
        await event_bus.publish(ChatMessageEvent(
            project_id=project_id,
            sender_id="system_progression",
            sender_type="ai",
            sender_name=sender_name,
            content=content,
        ))
        async with async_session_factory() as session:
            session.add(Message(
                project_id=project_id,
                sender_type="ai",
                sender_id="system_progression",
                sender_name=sender_name,
                content=content,
                stage=stage,
            ))
            await session.commit()
    except Exception:
        logger.debug("progression _say failed project=%s", project_id, exc_info=True)


async def _announce_transition(
    project_id: UUID, from_id: str, to_id: str | None, reason: str
) -> None:
    """兜底樣板轉場交代（教學透明）——不依賴 LLM 自願（修 Spec 27 §12.8/§12.10）。

    樣板字串只允許出現在本兜底路徑（04-03 §3.0.2）；常態路徑的轉場敘述
    由組長 LLM 生成（回顧＋肯定＋橋接）。
    """
    from_name = _name_of(from_id)
    if to_id is None:
        # 終局（define→completed）：結業交代由 closing 鏈負責，這裡只補一句收尾。
        body = f"「{from_name}」這一步我們先到這邊，接下來進入收尾。"
        await _say(project_id, body, _stage_of(from_id))
        return
    to_name = _name_of(to_id)
    if reason == "warmup_time_box":
        # 暖場兜底樣板（spec 28 §5.4）：坦白收尾＋帶橋接精神；不假裝達標。
        body = (
            "時間到了，暖場我們先收在這邊——剛剛大家丟的點子都很有意思。"
            "把這種「換個角度看熟悉東西」的勁帶著，"
            f"接下來進入「{to_name}」：聊聊你自己真實遇過的經驗。"
        )
    elif reason == "time_box":
        body = (
            f"我們在「{from_name}」這一步的時間差不多了，先帶著目前的成果，"
            f"接下來進入「{to_name}」。"
        )
    else:
        body = (
            f"「{from_name}」這一步我們做得差不多了，接下來進入「{to_name}」，"
            f"繼續往下走。"
        )
    await _say(project_id, body, _stage_of(to_id))


def _name_of(sub_id: str) -> str:
    """聊天交代用的「學生友善」階段名（去掉「講義第N步」等內部註記）。"""
    from app.stages.labels import student_facing_label

    sp = SUB_PHASES.get(sub_id)
    return student_facing_label(sp.name_zh) if sp is not None else sub_id


def _stage_of(sub_id: str) -> str:
    sp = SUB_PHASES.get(sub_id)
    return sp.macro_stage if sp is not None else "discover"
