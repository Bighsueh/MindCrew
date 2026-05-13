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
                # specs/16-timer-system.md §6.5.3：timer 事件廣播給所有訂閱者
                # （含觀察者）。payload 無 chat_id → should_deliver_chat_event
                # 走 None 分支自動放行。
                "timer_state",
                "timer_warning",
                "timer_timeout",
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
        logger.debug("Event bus forwarder ended: %s", exc)


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

    # ── 2. Check seat membership ───────────────────────────────────────────
    async with async_session_factory() as session:
        project = await _get_project(session, project_id)
        if project is None:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Teachers (creator) and seated users may connect
        has_seat = await _has_seat(session, project_id, user.id)
        is_creator = project.creator_id == user.id
        if not (has_seat or is_creator):
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
