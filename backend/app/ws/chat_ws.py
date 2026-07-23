from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_token
from app.chat.chat_id import make_group_chat_id, normalize_for_query
from app.config import settings
from app.db.models.message import Message
from app.db.models.project import Project
from app.db.models.seat import Seat
from app.db.models.user import User
from app.db.session import async_session_factory
from app.events.bus import event_bus
from app.events.handlers import handle_chat_message
from app.events.types import ChatMessageEvent, TypingEvent
from app.ws.connection_manager import chat_manager
from app.ws.delivery_filter import should_deliver_chat_event
from app.ws.presence_tracker import presence_tracker

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # seconds


async def _get_user_from_token(token: str) -> User | None:
    """Validate JWT and return User, or None on failure."""
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = UUID(user_id_str)
    except Exception:
        return None

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def _has_seat(session: AsyncSession, project_id: UUID, user_id: UUID) -> bool:
    result = await session.execute(
        select(Seat).where(
            Seat.project_id == project_id,
            Seat.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _get_project(session: AsyncSession, project_id: UUID) -> Project | None:
    result = await session.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def _resolve_user_seat_role(
    session: AsyncSession, project_id: UUID, user_id: UUID
) -> str | None:
    """查 user 在這個 project 佔有的席位（用於人類群組發話時的 cue 解除 hook）。

    回傳 seat_role 或 None（user 未入座 / 觀察者 / 其他狀態）。
    """
    result = await session.execute(
        select(Seat.seat_role).where(
            Seat.project_id == project_id,
            Seat.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _save_message(
    session: AsyncSession,
    project: Project,
    user: User,
    content: str,
    chat_id: str | None = None,
) -> Message:
    """寫一筆 human 訊息進 DB。

    Args:
        chat_id: 訊息所屬頻道；``None`` 代表向下相容的群組訊息
            （視同 ``{project_id}:group``）。個人訊息必須帶完整
            ``{project_id}:personal:{user_id}`` 字串，由 caller 在
            RBAC 過關後組好（見 spec 13 §6.2）。
    """
    msg = Message(
        project_id=project.id,
        sender_type="human",
        sender_id=str(user.id),
        sender_name=user.display_name,
        content=content,
        stage=project.current_stage,
        chat_id=chat_id,
    )
    session.add(msg)
    await session.flush()
    return msg


async def _publish_with_chat_id(event: ChatMessageEvent, chat_id: str | None) -> None:
    """Publish a ChatMessageEvent，並在 payload 注入 ``chat_id``。

    背景：Wave B3 才會將 ``chat_id`` 加入 ``ChatMessageEvent`` 的 dataclass
    欄位；在那之前，我們直接把 event 序列化後手動補上 ``chat_id``，再用
    event_bus 的 Redis 連線發佈，保持與 ``subscribe`` 對接的 JSON 結構一致。
    """
    event_dict = event.to_dict()
    event_dict["payload"]["chat_id"] = chat_id
    # 使用 event_bus 內部 redis client 直接發送，避免重複實作 channel 計算邏輯。
    redis = event_bus._assert_ready()  # noqa: SLF001
    channel = f"project:{event.project_id}:events"
    await redis.publish(channel, json.dumps(event_dict))


async def _heartbeat(ws: WebSocket) -> None:
    """Send periodic ping frames to keep the connection alive."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await ws.send_json({"type": "ping"})
        except Exception:
            break


_HUMAN_INPUT_DEBOUNCE_SECONDS = 1.5


async def _round_lock_human_input(
    project_id: UUID,
    user_id: UUID,
    content: str,
    sub_phase: str,
    arrival_ts: float | None = None,
) -> None:
    """真人群組 chat → 實質檢核 → 過則嘗試解鎖回合，不過則發 input_bounced。

    Phase 42 A2（spec 20 §11.4 / §12）。背景任務：失敗不影響訊息寫入流程。
    僅群組輸入呼叫（personal chat 不經此檢核、不解鎖，§4 / §12.1）。
    完整流程在 human_input_check.process_group_input（與 note 端點共用）。

    B1（多訊息連發）：`arrival_ts` 給定時做 **latest-wins debounce + 內容合併**——等
    ``_HUMAN_INPUT_DEBOUNCE_SECONDS`` 後若期間又有更新的人類群組訊息
    （``human_last_msg_ts`` > 本則 arrival_ts），代表這是連發中被取代的中間則 → 跳過；
    只由**最後一則** task 驅動，且它把**這波連發的所有內容合併**（``human_burst`` list）
    一起送實質檢核——故「打錯字訂正」（合併仍含完整點子）與「一段話拆多句」（合併＝完整段落、
    不只看最後一截）都驗得過。省 3 個並發 register_human_input 的 race + 連發的多次 tier-2 call。
    ``arrival_ts=None``＝不 debounce、不合併（向下相容；note 端點等非連發路徑）。
    """
    try:
        text_to_check = content
        if arrival_ts is not None:
            await asyncio.sleep(_HUMAN_INPUT_DEBOUNCE_SECONDS)
            try:
                r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                try:
                    latest_raw = await r.get(
                        f"project:{project_id}:human_last_msg_ts"
                    )
                    # 容 0.05s 抖動；更新訊息明顯較新 → 本則已被取代，交給最後一則處理。
                    if (
                        latest_raw is not None
                        and float(latest_raw) - arrival_ts > 0.05
                    ):
                        logger.debug(
                            "round_lock human input debounced (superseded) project=%s",
                            project_id,
                        )
                        return
                    # 我是最後一則 → 合併並清掉這波連發累積的內容，一起送檢核。
                    burst_key = f"project:{project_id}:human_burst"
                    parts = await r.lrange(burst_key, 0, -1)
                    await r.delete(burst_key)
                    if parts:
                        text_to_check = " ".join(p for p in parts if p) or content
                finally:
                    await r.aclose()
            except Exception:
                # debounce/合併失敗就用本則內容照常處理（不因防呆反而漏掉輸入）。
                text_to_check = content
                logger.debug(
                    "debounce/coalesce failed, using last msg project=%s",
                    project_id,
                    exc_info=True,
                )

        from app.agents.human_input_check import process_group_input

        await process_group_input(
            project_id, user_id, text_to_check, "chat", sub_phase
        )
    except Exception:
        logger.debug(
            "round_lock human input handling failed project=%s", project_id, exc_info=True
        )


async def _event_bus_forwarder(
    ws: WebSocket,
    project_id: UUID,
    viewer_user_id: str,
) -> None:
    """訂閱 EventBus 並把相關 event 轉送給該 client。

    Phase 20 / spec 13-personal-chat §6.2 §8.4：
    對每筆 event 從 payload 取 ``chat_id``，呼叫純函數
    ``should_deliver_chat_event`` 做 RBAC 過濾：
      - ``chat_id`` 為 None 或 ``:group`` 結尾 → 送出。
      - ``chat_id`` 為 ``...:personal:<viewer_user_id>`` → 送出。
      - ``chat_id`` 為別人的 personal 或未知格式 → 靜默丟棄。
    non-chat event（``seat_changed`` 等）payload 通常無 ``chat_id``，
    自動走 None 分支 → 廣播給所有人。
    """
    try:
        async for event_dict in event_bus.subscribe(project_id):
            event_type = event_dict.get("type")
            if event_type not in (
                "chat_message",
                "stage_changed",
                "micro_phase_changed",
                "seat_changed",
                "system_message",
                # ：timer 事件廣播給所有訂閱者
                # （含觀察者）。payload 無 chat_id → should_deliver_chat_event
                # 走 None 分支自動放行。
                "timer_state",
                "timer_warning",
                "timer_timeout",
                # ：Turn-Taking Controller 事件
                "turn_policy_changed",
                "cue",
                "turn_state",
                # Phase 42 A2：回合鎖凍結狀態 / 實質檢核退回提示（spec 20 §5.6/§5.7）。
                # payload 無 chat_id → 廣播給所有訂閱者（前端依 target_user_id 決定 UI）。
                "waiting_for_human",
                "input_bounced",
                # Phase 42 A3（WP7）：任務提示釘住 banner / 便條指認高亮。
                "user_task",
                "note_highlight",
                # Phase 42 D2（WP9 #9）：AI 發話/白板動作前置 typing 指示。
                # payload 無 chat_id → 廣播全房（僅群組 channel，個人 channel 不發）。
                "agent_typing",
                # Phase 42 D5（G14）：LLM fail-stop 全房暫停／恢復 banner（spec 20 §13.3/§13.4）。
                # payload 無 chat_id → 廣播給全房。
                "room_paused",
                "room_resumed",
            ):
                continue

            # 從 payload 取 chat_id；不依賴 dataclass 欄位是否齊備，
            # 純讀 dict 路徑，以避開 Wave B3 變更前的相容性問題。
            payload = event_dict.get("payload") or {}
            event_chat_id = payload.get("chat_id")

            if not should_deliver_chat_event(event_chat_id, viewer_user_id):
                logger.debug(
                    "WS forwarder drop event type=%s chat_id=%r viewer=%s",
                    event_type,
                    event_chat_id,
                    viewer_user_id,
                )
                continue

            try:
                await ws.send_json(event_dict)
            except Exception:
                break
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        # A-V 2026-06-12 教訓：forwarder 死亡曾因 debug 級 log 隱形數小時
        # （redis-py 8.0 pubsub TimeoutError 滅團）。非預期終止一律 warning。
        logger.warning("Event bus forwarder ended: %r", exc)


@router.websocket("/ws/project/{project_id}")
async def chat_websocket(ws: WebSocket, project_id: UUID) -> None:
    # ── 1. Authenticate via query param token ──────────────────────────────
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user = await _get_user_from_token(token)
    if user is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # ── 2. 存取守門：creator（參與）/ 列管老師・admin（旁觀）才可連線 ────────────
    async with async_session_factory() as session:
        project = await _get_project(session, project_id)
        if project is None:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        from app.projects.access import viewer_role_for

        if viewer_role_for(project, user) is None:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # ── 3. Accept & register ───────────────────────────────────────────────
    await ws.accept()
    chat_manager.connect(project_id, ws, user_id=user.id)
    presence_tracker.on_human_connect(project_id)
    logger.info("WS chat connected user=%s project=%s", user.id, project_id)

    heartbeat_task = asyncio.create_task(_heartbeat(ws))
    forwarder_task = asyncio.create_task(
        _event_bus_forwarder(ws, project_id, str(user.id))
    )

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from user=%s", user.id)
                continue

            msg_type = data.get("type")

            # ── chat_message ────────────────────────────────────────────
            if msg_type == "chat_message":
                payload = data.get("payload") or {}
                content: str = (payload.get("content") or "").strip()
                if not content:
                    continue

                # Phase 20 / spec 13-personal-chat §6.2：
                # 從 payload 取 chat_id 並做 RBAC 解析。
                # - None / "group" / "{pid}:group" → group（save 時帶完整 :group 字串）
                # - "personal" / "{pid}:personal:{self}" → personal（屬主已驗）
                # - 指向別人 personal / 未知格式 → log warning + 跳過該訊息
                raw_chat_id = payload.get("chat_id")
                try:
                    kind, normalized = normalize_for_query(
                        raw_chat_id, project_id, user.id
                    )
                except ValueError as exc:
                    logger.warning(
                        "WS chat RBAC violation: user=%s project=%s chat_id=%r err=%s",
                        user.id,
                        project_id,
                        raw_chat_id,
                        exc,
                    )
                    continue  # 安全地略過這筆，不關連線

                if kind == "personal":
                    # normalize_for_query 已保證 normalized 是 self 的字串。
                    chat_id_to_save: str | None = normalized
                else:
                    # group：寫入完整 ``{pid}:group`` 以便下游 query 與 forwarder 判斷一致。
                    chat_id_to_save = make_group_chat_id(project_id)

                async with async_session_factory() as session:
                    project = await _get_project(session, project_id)
                    if project is None:
                        continue
                    msg = await _save_message(
                        session, project, user, content, chat_id=chat_id_to_save
                    )
                    await session.commit()
                    created_at = msg.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    timestamp = created_at.isoformat()

                # ChatMessageEvent 目前 dataclass 尚未加 chat_id 欄位（Wave B3 處理）。
                # 透過 ``_publish_with_chat_id`` 在 to_dict 之後注入 chat_id，
                # 確保 forwarder 端能正確做 personal RBAC 過濾。
                event = ChatMessageEvent(
                    project_id=project_id,
                    sender_id=str(user.id),
                    sender_type="human",
                    sender_name=user.display_name,
                    content=content,
                    timestamp=timestamp,
                )
                await _publish_with_chat_id(event, chat_id_to_save)

                # Phase 28：人類在群組 chat 發話可能解除 cue（強版 cue-human 死鎖防護）。
                # personal chat 訊息不算對公開 cue 的回應，由 kind guard 過濾。
                # 全程背景任務，失敗不影響 user 訊息寫入流程。
                if kind == "group":
                    async with async_session_factory() as seat_session:
                        user_seat_role = await _resolve_user_seat_role(
                            seat_session, project_id, user.id
                        )
                    if user_seat_role:
                        from app.agents.turn_controller import (
                            notify_human_speak_in_group,
                        )

                        asyncio.create_task(
                            notify_human_speak_in_group(
                                project_id,
                                user_seat_role,
                                project.turn_policy,
                            )
                        )
                    # 人類在群組發話 → **無條件**清 awaiting-reply 鎖，讓 supervisor 下個
                    # tick 立刻接話。不再只清「等的剛好是發話者本人」的鎖——組長 @ 點名 crew
                    # 後若該 crew 結構上無法回應（如 0.0a 暖場 cued 下無放行機制），人類再發話
                    # 也清不掉 crew 鎖 → 組長乾等最久 120s＝死房。人類主動參與優先於等某 crew。
                    # 不依賴 user_seat_role（人類席位查不到時仍要清）。
                    from app.agents.supervisor.awaiting_reply import (
                        clear_awaiting_any,
                    )

                    asyncio.create_task(clear_awaiting_any(project_id))

                    # Phase 43（spec 20 §3/§11.7）：人類群組發話 → 喚醒休眠房
                    # （cued-hold 在線情境：被點名逾時休眠後再發話）。resume_room 自帶
                    # 守則——非 awaiting_human 暫停房 no-op，重連情境由 presence hook 處理。
                    from app.agents.room_hibernation import resume_room

                    asyncio.create_task(resume_room(project_id))

                    # 多訊息連發處理：記「人類最後一則群組訊息」時戳——**同步寫**（WS receive
                    # loop 逐則處理，連發 3 則時最終值＝最後一則的 ts，不靠並發 task 的順序）。
                    # 供 (B1) _round_lock_human_input 的 latest-wins debounce 比對、(B2) assess
                    # Rule 2.5 近期 debounce 共用。
                    arrival_ts = time.time()
                    try:
                        _r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                        try:
                            await _r.set(
                                f"project:{project_id}:human_last_msg_ts",
                                str(arrival_ts),
                                ex=3,
                            )
                            # B1 內容合併：累積這波連發的各則內容（依到達順序），最後一則
                            # task 合併後一起送實質檢核（一段話拆多句也驗得過、不只看最後一截）。
                            _burst_key = f"project:{project_id}:human_burst"
                            await _r.rpush(_burst_key, content)
                            await _r.expire(_burst_key, 4)
                        finally:
                            await _r.aclose()
                    except Exception:
                        logger.debug(
                            "human_last_msg_ts/burst set failed", exc_info=True
                        )

                    # Phase 42 A2：群組輸入 → 實質檢核 + 回合鎖解鎖（spec 20 §11.4/§12）。
                    # 不依賴 user_seat_role（回合鎖以 seats 查詢辨識真人席）。
                    # B1：傳 arrival_ts → task latest-wins debounce（連發只最後一則跑檢核，
                    # 省並發 register_human_input race + 連發的 tier-2 LLM call）。
                    sub_phase_now = (
                        project.current_sub_phase or project.current_stage or ""
                    ).strip()
                    if sub_phase_now:
                        asyncio.create_task(
                            _round_lock_human_input(
                                project_id, user.id, content, sub_phase_now, arrival_ts
                            )
                        )

                # Phase-3 hook – 個人訊息不入 group chat cache，handler 路徑
                # 仍呼叫但靠下游（events/handlers.py Wave B3）依 chat_id 過濾。
                asyncio.create_task(handle_chat_message(
                    project_id, str(user.id), content,
                    sender_name=user.display_name, sender_type="human",
                ))

                # Phase 20 Step 17.6（spec §7.2 WS 路徑）：
                # 個人聊天訊息 → 觸發 DT 教練背景任務產生回覆。
                # micro_phase 在 WS payload 中可能未帶；若缺則 fallback 為 stage。
                if kind == "personal":
                    micro_phase = (
                        (payload.get("micro_phase") or "")
                        .strip()
                        or project.current_stage
                    )
                    # 延後 import 以避免 circular import（coach service 也會 import
                    # app.chat / app.events 等本模組依賴的物件）。
                    from app.coach.service import dt_coach_service

                    asyncio.create_task(
                        dt_coach_service.reply_to_personal_message(
                            project_id=project_id,
                            user_id=user.id,
                            user_display_name=user.display_name,
                            stage=project.current_stage,
                            micro_phase=micro_phase,
                            user_message_content=content,
                        )
                    )

            # ── agent_action (Phase 28) ─────────────────────────────────
            # ：學生在前端按 Pass / Raise-Hand 時
            # 走這個分支。Pass 推進 TurnController 狀態 (RR 模式下 advance queue
            # 即可讓出輪次)；Raise-Hand 寫 Redis 旗標，Open-Floor controller 下個
            # tick 會讓人類優先 1 個窗口。
            elif msg_type == "agent_action":
                payload = data.get("payload") or {}
                action = (payload.get("action") or "").strip().lower()
                seat_role = (payload.get("seat_role") or "").strip()
                if not seat_role:
                    logger.warning(
                        "agent_action missing seat_role user=%s project=%s",
                        user.id, project_id,
                    )
                    continue
                # 驗證 seat 真的是這個 user 的（防偽造）
                async with async_session_factory() as session:
                    seat_check = await session.execute(
                        select(Seat).where(
                            Seat.project_id == project_id,
                            Seat.user_id == user.id,
                            Seat.seat_role == seat_role,
                        )
                    )
                    if seat_check.scalar_one_or_none() is None:
                        logger.warning(
                            "agent_action seat mismatch user=%s seat=%s",
                            user.id, seat_role,
                        )
                        continue

                if action == "raise_hand":
                    from app.agents.turn_controller import mark_user_priority_speak

                    await mark_user_priority_speak(project_id, seat_role)
                    logger.info(
                        "User raise_hand project=%s seat=%s", project_id, seat_role
                    )
                elif action == "pass":
                    # 取當前 controller 並呼叫 on_pass。每次重取 = 即時感受 PATCH 切換。
                    from app.agents.cue_timeout_watcher import (
                        cancel_cue_timeout_watcher,
                    )
                    from app.agents.turn_controller import get_controller

                    async with async_session_factory() as session:
                        project = await _get_project(session, project_id)
                        if project is None:
                            continue
                        policy_value = getattr(project, "turn_policy", "cued")
                    controller = await get_controller(policy_value, project_id)
                    await controller.on_pass(seat_role, {"my_seat": seat_role})
                    # Phase 28 B4：pass 解除 cue → cancel timeout watcher 避免誤觸 retry
                    cancel_cue_timeout_watcher(project_id, seat_role)
                    logger.info(
                        "User pass project=%s seat=%s policy=%s",
                        project_id, seat_role, policy_value,
                    )
                else:
                    logger.debug(
                        "Unknown agent_action %r from user=%s", action, user.id
                    )

            # ── typing indicators ───────────────────────────────────────
            elif msg_type in ("typing_start", "typing_stop"):
                is_typing = msg_type == "typing_start"
                typing_event = TypingEvent(
                    project_id=project_id,
                    user_name=user.display_name,
                    is_typing=is_typing,
                )
                await chat_manager.broadcast(project_id, typing_event.to_dict())
                # Write typing timestamp to Redis for agent ASSESS Rule 2
                if is_typing:
                    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                    try:
                        await r.set(
                            f"project:{project_id}:human_typing_ts",
                            str(time.time()),
                            ex=5,
                        )
                    finally:
                        await r.aclose()

            # ── liveness ping/pong（client/server 心跳）── 明確 no-op：不關連線、不刷 debug。
            elif msg_type in ("ping", "pong"):
                continue

            else:
                logger.debug("Unknown message type=%s from user=%s", msg_type, user.id)

    except WebSocketDisconnect:
        logger.info("WS chat disconnected user=%s project=%s", user.id, project_id)
    except Exception as exc:
        logger.exception("WS chat error user=%s project=%s: %s", user.id, project_id, exc)
    finally:
        heartbeat_task.cancel()
        forwarder_task.cancel()
        chat_manager.disconnect(project_id, ws)
        presence_tracker.on_human_disconnect(project_id)
