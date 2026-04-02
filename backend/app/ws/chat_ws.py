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
) -> Message:
    msg = Message(
        project_id=project.id,
        sender_type="human",
        sender_id=str(user.id),
        sender_name=user.display_name,
        content=content,
        stage=project.current_stage,
    )
    session.add(msg)
    await session.flush()
    return msg


async def _heartbeat(ws: WebSocket) -> None:
    """Send periodic ping frames to keep the connection alive."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await ws.send_json({"type": "ping"})
        except Exception:
            break


async def _event_bus_forwarder(ws: WebSocket, project_id: UUID) -> None:
    """Subscribe to the EventBus and forward relevant events to this client."""
    try:
        async for event_dict in event_bus.subscribe(project_id):
            event_type = event_dict.get("type")
            if event_type in ("chat_message", "stage_changed", "micro_phase_changed", "seat_changed", "system_message"):
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
    chat_manager.connect(project_id, ws)
    presence_tracker.on_human_connect(project_id)
    logger.info("WS chat connected user=%s project=%s", user.id, project_id)

    heartbeat_task = asyncio.create_task(_heartbeat(ws))
    forwarder_task = asyncio.create_task(_event_bus_forwarder(ws, project_id))

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
                content: str = (data.get("payload") or {}).get("content", "").strip()
                if not content:
                    continue

                async with async_session_factory() as session:
                    project = await _get_project(session, project_id)
                    if project is None:
                        continue
                    msg = await _save_message(session, project, user, content)
                    await session.commit()
                    created_at = msg.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    timestamp = created_at.isoformat()

                event = ChatMessageEvent(
                    project_id=project_id,
                    sender_id=str(user.id),
                    sender_type="human",
                    sender_name=user.display_name,
                    content=content,
                    timestamp=timestamp,
                )
                # Publish to Redis — _event_bus_forwarder delivers to all WS clients
                # (single delivery path, consistent with AI message flow)
                await event_bus.publish(event)
                # Phase-3 hook – currently a noop
                asyncio.create_task(handle_chat_message(
                    project_id, str(user.id), content,
                    sender_name=user.display_name, sender_type="human",
                ))

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
