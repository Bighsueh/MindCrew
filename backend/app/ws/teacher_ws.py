from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.auth.jwt import decode_token
from app.db.models.project import Project
from app.db.models.user import User
from app.db.session import async_session_factory
from app.events.bus import event_bus
from app.ws.presence_tracker import presence_tracker

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # seconds


async def _get_teacher_from_token(token: str) -> User | None:
    """Validate JWT, ensure role == 'teacher', return User or None."""
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
        user = result.scalar_one_or_none()
        if user is None or user.role != "teacher":
            return None
        return user


async def _heartbeat(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await ws.send_json({"type": "ping"})
        except Exception:
            break


@router.websocket("/ws/teacher/{user_id}")
async def teacher_websocket(ws: WebSocket, user_id: UUID) -> None:
    # ── 1. Authenticate ────────────────────────────────────────────────────
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user = await _get_teacher_from_token(token)
    if user is None or user.id != user_id:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # ── 2. Accept ──────────────────────────────────────────────────────────
    await ws.accept()
    logger.info("WS teacher connected user=%s", user_id)

    # Register teacher presence for all their projects
    teacher_project_ids: list[UUID] = []
    async with async_session_factory() as session:
        rows = await session.execute(
            select(Project.id).where(Project.creator_id == user_id)
        )
        teacher_project_ids = [row[0] for row in rows.all()]

    for pid in teacher_project_ids:
        presence_tracker.on_human_connect(pid)

    heartbeat_task = asyncio.create_task(_heartbeat(ws))

    try:
        async for event_dict in event_bus.subscribe_teacher(user_id):
            event_type = event_dict.get("type")
            if event_type == "project_update":
                try:
                    await ws.send_json(event_dict)
                except Exception:
                    break
    except WebSocketDisconnect:
        logger.info("WS teacher disconnected user=%s", user_id)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.exception("WS teacher error user=%s: %s", user_id, exc)
    finally:
        heartbeat_task.cancel()
        for pid in teacher_project_ids:
            presence_tracker.on_human_disconnect(pid)
        logger.info("WS teacher cleaned up user=%s", user_id)
