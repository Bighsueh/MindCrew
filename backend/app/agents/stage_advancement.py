"""Stage advancement logic (execution layer).

Extracted from evaluator.py to keep files under 500 lines.

Phase 29 (2026-05-26): system scope reduced to the first diamond only.
- ``_STAGE_ORDER`` no longer contains ``develop`` / ``deliver``.
- When ``current_stage == 'define'`` and the team advances past ``2.3``,
  ``advance_stage()`` writes ``current_stage = 'completed'`` and emits
  ``FirstDiamondCompletedEvent`` (Phase 34 will hook the closing ritual onto
  this event). Spec/04-06-micro-phase-state.md §4.2.

Phase 42 A1 (spec 04-06 §5.8 v4.25): 推進權改組長節奏推進——
- ``propose_advance``（macro 60s 同意窗、沉默＝同意）已移除；常態推進由組長
  宣布（act `advance_sub_phase`）、watcher 僅兜底（progression/watcher.py）。
- ``advance_micro_phase`` / ``advance_sub_phase`` 新增 ``announce`` 參數：
  組長路徑與 watcher 兜底傳 False（轉場敘述由組長 LLM 生成或 watcher 樣板
  負責，spec 04-03 §3.0.2——樣板字串只允許出現在兜底路徑）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from app.agents.blackboard import BlackboardManager
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# Phase 29: develop / deliver removed.
# 'completed' is a terminal state reached after Define (2.3) is finalized.
# 暖場(warmup)為第一級 macro stage:專案先進 warmup(Alternative Uses 破冰遊戲),
# 暖完才進 discover。navbar 顯示三階段(暖場/發現/定義)。
_STAGE_ORDER = ["warmup", "discover", "define", "completed"]

_STAGE_NAMES = {
    "warmup": "暖場",
    "discover": "發現",
    "define": "定義",
    "completed": "第一鑽石完成",
}

def get_next_stage(current: str) -> str | None:
    """Return the next stage in the Design Thinking sequence, or None.

    Phase 29: define → completed is the new terminal transition.
    """
    try:
        idx = _STAGE_ORDER.index(current)
        if idx + 1 < len(_STAGE_ORDER):
            return _STAGE_ORDER[idx + 1]
    except ValueError:
        pass
    return None


# Phase 42 A1：propose_advance（macro 60s 同意窗、沉默＝同意）已移除（spec 04-06
# §4.2/§5.8 v4.25、brief §9-13）。人類拍板改落 per-cell 真人 gate（2.6 拍板、
# 2.7 確認）；macro 邊界同走組長宣布推進。stage_evaluation_log.action_taken 的
# 'propose_advance' 為歷史值，僅供舊 row 解讀、v4.25 起不再寫入（spec 06 §1.8）。


async def advance_stage(
    current_stage: str,
    project_id: UUID,
    agent_id: str,
    blackboard: BlackboardManager | None = None,
) -> str:
    """Directly advance the project to the next stage.

    Phase 29: when next_stage == 'completed', also emits FirstDiamondCompletedEvent
    so downstream listeners (Phase 34 closing ritual, UI banner) can react.
    """
    next_stage = get_next_stage(current_stage)
    if not next_stage:
        logger.info("Already at final stage: %s", current_stage)
        return "already_final_stage"

    is_terminal = next_stage == "completed"

    try:
        async with async_session_factory() as session:
            from sqlalchemy import update
            from app.db.models.project import Project
            from app.db.models.stage_history import StageHistory  # type: ignore[attr-defined]

            now = datetime.now(timezone.utc)

            # 同步更新 current_micro_phase（修復 macro boundary crossing bug — Phase 13）
            from app.stages.micro_phases import get_first_micro_phase_for_stage
            from app.stages.sub_phases import get_first_sub_phase_of_macro
            first_micro = (
                get_first_micro_phase_for_stage(next_stage)
                if not is_terminal
                else None
            )
            first_sub = (
                get_first_sub_phase_of_macro(next_stage)
                if not is_terminal
                else None
            )
            update_values: dict = {"current_stage": next_stage, "updated_at": now}
            if first_micro:
                update_values["current_micro_phase"] = first_micro
            if first_sub:
                update_values["current_sub_phase"] = first_sub

            # Phase 42 A1：CAS guard——組長 action 與 watcher 兜底是兩個併發寫者，
            # 以 current_stage 條件確保「已被別人推進」時本次成為 no-op，不重複跨階。
            cas_result = await session.execute(
                update(Project)
                .where(
                    Project.id == project_id,
                    Project.current_stage == current_stage,
                )
                .values(**update_values)
            )
            if cas_result.rowcount == 0:
                await session.rollback()
                logger.info(
                    "advance_stage noop（已被其他路徑推進）project=%s from=%s",
                    project_id, current_stage,
                )
                return "stage_advance_noop:already_advanced"

            # Capture canvas snapshot (Phase 16: fix NULL snapshot for AI-triggered transitions)
            canvas_snapshot = None
            try:
                from app.canvas.tools_perception import get_canvas_snapshot
                canvas_snapshot = await get_canvas_snapshot(project_id)
            except Exception:
                pass

            sh = StageHistory(
                project_id=project_id,
                from_stage=current_stage,
                to_stage=next_stage,
                triggered_by="ai_evaluator",
                canvas_snapshot=canvas_snapshot,
            )
            session.add(sh)
            await session.commit()

        from app.events.types import StageChangedEvent
        from app.events.bus import event_bus

        event = StageChangedEvent(
            project_id=project_id,
            from_stage=current_stage,
            to=next_stage,
            triggered_by="ai_evaluator",
        )
        await event_bus.publish(event)

        # Phase 29: 第一鑽石終局 — emit FirstDiamondCompletedEvent
        # Phase 34: 同時觸發 closing ritual（best-effort，失敗不影響 stage advance）
        if is_terminal:
            try:
                from app.events.types import FirstDiamondCompletedEvent

                fd_event = FirstDiamondCompletedEvent(
                    project_id=project_id,
                    triggered_by=agent_id,
                )
                await event_bus.publish(fd_event)
            except Exception as exc:
                logger.warning(
                    "Failed to publish FirstDiamondCompletedEvent: %s", exc
                )
            try:
                from app.agents.first_diamond_closing import (
                    trigger_first_diamond_closing,
                )

                await trigger_first_diamond_closing(project_id, agent_id)
            except Exception as exc:
                logger.warning(
                    "First diamond closing ritual failed: %s", exc
                )

        # ：macro 切換時重啟 timer 到新 sub_phase
        if first_sub:
            try:
                from app.timer.service import TimerService
                await TimerService.start_phase(project_id, first_sub)
            except Exception as exc:
                logger.debug("Timer start_phase on advance_stage failed: %s", exc)

        # Phase 42 A1：呼叫端沒帶 blackboard（組長 action / watcher 兜底經
        # advance_router）時自建一個——跨 stage 必須清掉舊 stage 的殘留
        # directive/saturation，否則污染新 stage 的 context。
        if not is_terminal:
            bb = blackboard or BlackboardManager(
                project_id=project_id,
                agent_id=agent_id,
                seat_role="supervisor",
            )
            try:
                await bb.clear_stage(next_stage)
            except Exception as exc:
                logger.debug("blackboard clear_stage failed: %s", exc)

        # Spec 13: Organization Turn 已廢除。Canvas 整理改由收斂期 prompt 偏好自然完成（Phase 41：原 silent_rearrange 已移除）。

        logger.info(
            "Project %s advanced: %s → %s",
            project_id,
            current_stage,
            next_stage,
        )
        return f"advanced_to_{next_stage}"
    except Exception as exc:
        logger.error("Failed to advance stage: %s", exc)
        return "advance_failed"


async def advance_micro_phase(
    project_id: UUID,
    agent_id: str,
    from_phase: str,
    to_phase: str,
    announce: bool = True,
) -> str:
    """Advance micro phase via direct DB update (within same macro stage).

    Returns the new micro phase ID prefixed with 'micro_advanced_to_'.

    Phase 42 A1: ``announce=False`` 抑制系統樣板轉場公告——組長宣布路徑
    （轉場由組長 LLM 生成）與 watcher 兜底（自帶歸因樣板）使用。
    """
    try:
        async with async_session_factory() as session:
            from sqlalchemy import update
            from app.db.models.project import Project
            from app.db.models.micro_phase_history import MicroPhaseHistory  # type: ignore[attr-defined]
            from app.stages.sub_phases import get_first_sub_phase_of_micro

            now = datetime.now(timezone.utc)

            # ：micro_phase 切換時同步把 sub_phase
            # 推到對應 micro 的第一個 sub，timer 才會跟上。
            first_sub = get_first_sub_phase_of_micro(to_phase)
            mp_update_values: dict = {
                "current_micro_phase": to_phase,
                "updated_at": now,
            }
            if first_sub:
                mp_update_values["current_sub_phase"] = first_sub

            # Phase 42 A1：CAS guard（同 advance_stage——防組長/watcher 雙寫重複跨界）。
            cas_result = await session.execute(
                update(Project)
                .where(
                    Project.id == project_id,
                    Project.current_micro_phase == from_phase,
                )
                .values(**mp_update_values)
            )
            if cas_result.rowcount == 0:
                await session.rollback()
                logger.info(
                    "advance_micro_phase noop（已被其他路徑推進）project=%s from=%s",
                    project_id, from_phase,
                )
                return "micro_advance_noop:already_advanced"

            mp_hist = MicroPhaseHistory(
                project_id=project_id,
                from_micro_phase=from_phase,
                to_micro_phase=to_phase,
                transition_type="advance",
                triggered_by=agent_id,
            )
            session.add(mp_hist)
            await session.commit()

            # Publish event INSIDE the try block right after commit
            # to prevent split-transaction (DB committed but event not sent)
            from app.events.types import MicroPhaseChangedEvent
            from app.events.bus import event_bus

            event = MicroPhaseChangedEvent(
                project_id=project_id,
                from_phase=from_phase,
                to_phase=to_phase,
                transition_type="advance",
                triggered_by=agent_id,
            )
            await event_bus.publish(event)

            # ：重啟 timer 到新 sub_phase 預算
            if first_sub:
                try:
                    from app.timer.service import TimerService
                    await TimerService.start_phase(project_id, first_sub)
                except Exception as exc:
                    logger.debug(
                        "Timer start_phase on advance_micro_phase failed: %s", exc
                    )

        # Announce transition via chat (best-effort, outside DB session)
        # Phase 42 A1：announce=False（組長路徑/watcher 兜底）時不發系統樣板。
        if announce:
            try:
                from app.stages.micro_phases import get_micro_phase
                from app.events.types import ChatMessageEvent
                from app.events.bus import event_bus as _eb
                from app.chinese.converter import chinese_converter
                from app.agents.personas.display import resolve_display_name
                from app.stages.labels import student_facing_label

                try:
                    mp = get_micro_phase(to_phase)
                    phase_name = mp.name_zh
                except KeyError:
                    phase_name = to_phase

                announcement = chinese_converter.convert(
                    f"我們已完成上一步驟，現在進入「{student_facing_label(phase_name)}」階段。"
                )
                chat_event = ChatMessageEvent(
                    project_id=project_id,
                    sender_id=agent_id,
                    sender_type="ai",
                    sender_name=resolve_display_name("supervisor"),
                    content=announcement,
                )
                await _eb.publish(chat_event)
            except Exception as exc:
                logger.warning("Failed to announce micro phase transition: %s", exc)

        # Spec 13: Organization Turn 已廢除。Canvas 整理改由收斂期 prompt 偏好自然完成（Phase 41：原 silent_rearrange 已移除）。

        logger.info(
            "Project %s micro phase advanced: %s → %s",
            project_id,
            from_phase,
            to_phase,
        )
        return f"micro_advanced_to_{to_phase}"
    except Exception as exc:
        logger.error("Failed to advance micro phase: %s", exc)
        return "micro_advance_failed"


# ---------------------------------------------------------------------------
# Spec 13 — Sub-phase advancement
# ---------------------------------------------------------------------------

async def advance_sub_phase(
    project_id: UUID,
    agent_id: str,
    from_sub_phase: str | None,
    to_sub_phase: str,
    skip_deliverable_check: bool = False,
    announce: bool = True,
) -> str:
    """Update project.current_sub_phase and broadcast.

    Spec 14 A9: 推進前先檢查 from_sub_phase 的 deliverables_required 是否達成。
    teacher 強制推進可傳 skip_deliverable_check=True。

    Also clears reveal queue + resets stability timer when entering a new sub-phase.

    Phase 42 A1: ``announce=False`` 抑制「接下來進入「X」」系統樣板——組長宣布
    路徑（轉場由組長 LLM 生成）與 watcher 兜底（自帶歸因樣板）使用。
    """
    # Spec 14 A9: Deliverable check
    if from_sub_phase and not skip_deliverable_check:
        try:
            from app.stages.deliverables import check_deliverables
            check = await check_deliverables(project_id, from_sub_phase)
            if not check.passed:
                logger.info(
                    "Sub-phase advance blocked project=%s from=%s missing=%s",
                    project_id, from_sub_phase, check.missing,
                )
                return f"sub_advance_blocked:{'; '.join(check.missing)}"
        except Exception as exc:
            logger.warning("Deliverable check raised %s — proceed", exc)

    # Phase 33 (spec/25-artifact-gate.md): template-bounded artifact gate.
    # Complementary to deliverables (zone-bounded). Teacher / system advance
    # bypasses both via ``skip_deliverable_check=True``.
    if from_sub_phase and not skip_deliverable_check:
        try:
            from app.canvas.artifact_gate import (
                check_artifact_gate,
                format_gate_rejection_zh,
            )

            gate = await check_artifact_gate(project_id, from_sub_phase)
            if not gate.passed:
                logger.info(
                    "Sub-phase advance blocked by artifact_gate project=%s "
                    "from=%s missing=%s",
                    project_id, from_sub_phase, gate.missing,
                )
                # ArtifactGateRejectedEvent 已廢除（spec 25 v2.1 §4，Phase 42 補正 R2）：
                # 前端從未接、payload 帶機器鍵名；回饋走組長代言＋結果字串兩條活路徑。
                rejection_text = format_gate_rejection_zh(gate)
                return f"sub_advance_blocked:artifact_gate:{rejection_text}"
        except Exception as exc:
            logger.warning("Artifact gate raised %s — proceed", exc)

    try:
        async with async_session_factory() as session:
            from sqlalchemy import update
            from app.db.models.project import Project

            now = datetime.now(timezone.utc)
            # Phase 42 A1：CAS guard——from_sub_phase 已知時帶條件更新，
            # 組長 action 與 watcher 兜底併發時後到者成為 no-op（不跳格）。
            stmt = update(Project).where(Project.id == project_id)
            if from_sub_phase:
                stmt = stmt.where(Project.current_sub_phase == from_sub_phase)
            cas_result = await session.execute(
                stmt.values(current_sub_phase=to_sub_phase, updated_at=now)
            )
            if cas_result.rowcount == 0:
                await session.rollback()
                logger.info(
                    "advance_sub_phase noop（已被其他路徑推進）project=%s from=%s",
                    project_id, from_sub_phase,
                )
                return "sub_advance_noop:already_advanced"
            await session.commit()

        # Spec 15 B5: Start timer for new sub_phase
        try:
            from app.timer.service import TimerService
            await TimerService.start_phase(project_id, to_sub_phase)
        except Exception as exc:
            logger.debug("Timer start_phase failed: %s", exc)

        # Reset reveal queue / stability timer
        try:
            from app.agents.reveal_queue import reset as reset_reveal, start_reveal_round
            from app.canvas.stability_detector import reset as reset_stability
            await reset_reveal(project_id)
            await reset_stability(project_id)

            # Spec 14 A11: 進入 reveal_round comm_mode 自動啟動輪序
            try:
                from app.stages.sub_phases import get_sub_phase as _gsp
                target_sp = _gsp(to_sub_phase)
                if target_sp.comm_modes and target_sp.comm_modes[0] == "reveal_round":
                    seat_order = await _load_seat_order_for_reveal(project_id)
                    if seat_order:
                        await start_reveal_round(
                            project_id, seat_order, to_sub_phase,
                        )
                        logger.info(
                            "Reveal round started project=%s seats=%s",
                            project_id, seat_order,
                        )
            except Exception as exc:
                logger.debug("Auto-start reveal round failed: %s", exc)
        except Exception as exc:
            logger.debug("Reset reveal/stability failed: %s", exc)

        # Broadcast SubPhaseChangedEvent if available
        try:
            from app.events.types import SubPhaseChangedEvent  # type: ignore[attr-defined]
            from app.events.bus import event_bus
            event = SubPhaseChangedEvent(  # type: ignore[call-arg]
                project_id=project_id,
                from_sub_phase=from_sub_phase,
                to_sub_phase=to_sub_phase,
                triggered_by=agent_id,
            )
            await event_bus.publish(event)
        except (ImportError, AttributeError):
            # Event type not yet defined; OK
            pass

        # 進入新 sub_phase → 自動畫出該 phase 宣告的 zones（dashed 框 + 註冊 bounds），
        # 否則 agent 的 create_note 會全部落在「無 active zone」而被硬拒絕（白板空白）。
        try:
            from app.canvas.zone_seed import seed_zones_for_sub_phase
            await seed_zones_for_sub_phase(project_id, to_sub_phase)
        except Exception as exc:
            logger.debug("Zone seed on sub_phase advance failed: %s", exc)

        # Announce in chat
        # Phase 42 A1：announce=False（組長路徑/watcher 兜底）時不發系統樣板。
        if announce:
            try:
                from app.stages.sub_phases import get_sub_phase
                from app.events.types import ChatMessageEvent
                from app.events.bus import event_bus as _eb
                from app.chinese.converter import chinese_converter
                from app.agents.personas.display import resolve_display_name
                from app.stages.labels import student_facing_label

                try:
                    sp = get_sub_phase(to_sub_phase)
                    name = sp.name_zh
                except KeyError:
                    name = to_sub_phase

                announcement = chinese_converter.convert(
                    f"接下來進入「{student_facing_label(name)}」。"
                )
                chat_event = ChatMessageEvent(
                    project_id=project_id,
                    sender_id=agent_id,
                    sender_type="ai",
                    sender_name=resolve_display_name("supervisor"),
                    content=announcement,
                )
                await _eb.publish(chat_event)
            except Exception as exc:
                logger.debug("Sub-phase announcement failed: %s", exc)

        logger.info(
            "Sub-phase advanced project=%s %s → %s",
            project_id, from_sub_phase, to_sub_phase,
        )
        return f"sub_advanced_to_{to_sub_phase}"
    except Exception as exc:
        logger.error("Failed to advance sub_phase: %s", exc)
        return "sub_advance_failed"


async def _load_seat_order_for_reveal(project_id: UUID) -> list[str]:
    """Spec 14 A11: 載入該 project 的 seat 順序（supervisor 後 crew_1..4）。

    Reveal round 順序：supervisor 開頭，後 crew_1, crew_2, crew_3, crew_4。
    """
    from sqlalchemy import select
    from app.db.models.seat import Seat

    async with async_session_factory() as session:
        rows = await session.execute(
            select(Seat).where(Seat.project_id == project_id)
        )
        seats = rows.scalars().all()

    # Filter ai seats only (人類 reveal 不從 queue 強制)
    ai_seats = [s.seat_role for s in seats if s.occupant_type == "ai"]
    # Sort: supervisor first, then crew_N by numeric suffix
    def _sort_key(role: str) -> tuple[int, int]:
        if role == "supervisor":
            return (0, 0)
        if role.startswith("crew_"):
            try:
                return (1, int(role.split("_")[1]))
            except (IndexError, ValueError):
                return (2, 0)
        return (3, 0)

    return sorted(ai_seats, key=_sort_key)
