"""Simplified canvas-sync WebSocket endpoint.

Accepts connections at /ws/canvas/{project_id}?token=<JWT>.
- Broadcasts canvas state changes (published to Redis project:{id}:canvas channel)
  to all connected clients.
- Receives canvas operations from frontend clients and applies them via canvas_ops.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

import redis.asyncio as aioredis

from app.auth.jwt import decode_token
from app.bridge.canvas_ops import canvas_ops
from app.config import settings
from app.db.models.user import User
from app.db.session import async_session_factory
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # seconds


# ---------------------------------------------------------------------------
# Simple per-project connection registry (in-process only)
# ---------------------------------------------------------------------------

class _CanvasConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, list[WebSocket]] = {}

    def connect(self, project_id: UUID, ws: WebSocket) -> None:
        self._connections.setdefault(project_id, []).append(ws)

    def disconnect(self, project_id: UUID, ws: WebSocket) -> None:
        conns = self._connections.get(project_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, project_id: UUID, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(project_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(project_id, ws)


canvas_manager = _CanvasConnectionManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_from_token(token: str) -> User | None:
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


async def _heartbeat(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await ws.send_json({"type": "ping"})
        except Exception:
            break


async def _redis_forwarder(ws: WebSocket, project_id: UUID) -> None:
    """Subscribe to the Redis canvas channel and forward updates to this client."""
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        channel = f"project:{project_id}:canvas"
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        async for raw in pubsub.listen():
            if raw["type"] != "message":
                continue
            try:
                data = json.loads(raw["data"])
                await ws.send_json(data)
            except Exception:
                break
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.debug("Canvas redis forwarder ended: %s", exc)
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await r.aclose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/yjs/{project_id}")
async def canvas_websocket(ws: WebSocket, project_id: UUID) -> None:
    # 1. Auth
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user = await _get_user_from_token(token)
    if user is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Accept
    await ws.accept()
    canvas_manager.connect(project_id, ws)
    logger.info("WS canvas connected user=%s project=%s", user.id, project_id)

    # 3. Send current state immediately
    try:
        state = await canvas_ops.get_canvas_state(project_id)
        await ws.send_json({"type": "canvas_state", "payload": state})
    except Exception as exc:
        logger.warning("Failed to send initial canvas state: %s", exc)

    heartbeat_task = asyncio.create_task(_heartbeat(ws))
    forwarder_task = asyncio.create_task(_redis_forwarder(ws, project_id))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from user=%s on canvas WS", user.id)
                continue

            op_type = data.get("type")
            payload = data.get("payload", {})

            # Handle canvas operations sent by the frontend
            if op_type == "add_note":
                await canvas_ops.add_note(
                    project_id=project_id,
                    content=payload.get("content", ""),
                    position=payload.get("position"),
                    color=payload.get("color", "yellow"),
                    author_id=str(user.id),
                    author_name=user.display_name,
                    author_type="human",
                )
            elif op_type == "move_note":
                await canvas_ops.move_note(
                    project_id=project_id,
                    note_id=payload.get("note_id", ""),
                    target_group=payload.get("target_group"),
                )
            elif op_type == "edit_note":
                await canvas_ops.edit_note(
                    project_id=project_id,
                    note_id=payload.get("note_id", ""),
                    new_content=payload.get("content", ""),
                )
            elif op_type == "delete_note":
                await canvas_ops.delete_note(
                    project_id=project_id,
                    note_id=payload.get("note_id", ""),
                )
            elif op_type == "group_notes":
                await canvas_ops.group_notes(
                    project_id=project_id,
                    note_ids=payload.get("note_ids", []),
                    group_name=payload.get("group_name", ""),
                )
            elif op_type == "get_state":
                state = await canvas_ops.get_canvas_state(project_id)
                await ws.send_json({"type": "canvas_state", "payload": state})
            else:
                logger.debug("Unknown canvas op type=%s from user=%s", op_type, user.id)

    except WebSocketDisconnect:
        logger.info("WS canvas disconnected user=%s project=%s", user.id, project_id)
    except Exception as exc:
        logger.exception("WS canvas error user=%s project=%s: %s", user.id, project_id, exc)
    finally:
        heartbeat_task.cancel()
        forwarder_task.cancel()
        canvas_manager.disconnect(project_id, ws)
