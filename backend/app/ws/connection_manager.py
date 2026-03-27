from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections grouped by project_id."""

    def __init__(self) -> None:
        # project_id (str) → set of WebSocket
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    def connect(self, project_id: UUID, ws: WebSocket) -> None:
        key = str(project_id)
        self._connections[key].add(ws)
        logger.debug(
            "WS connected project=%s total=%d", key, len(self._connections[key])
        )

    def disconnect(self, project_id: UUID, ws: WebSocket) -> None:
        key = str(project_id)
        self._connections[key].discard(ws)
        if not self._connections[key]:
            del self._connections[key]
        logger.debug("WS disconnected project=%s", key)

    async def broadcast(self, project_id: UUID, message: dict) -> None:
        """Send a JSON-serialisable dict to all connections in a project."""
        key = str(project_id)
        connections = list(self._connections.get(key, set()))
        if not connections:
            return
        tasks = [ws.send_json(message) for ws in connections]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for ws, result in zip(connections, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Failed to send message to a client in project=%s: %s", key, result
                )

    def connection_count(self, project_id: UUID) -> int:
        return len(self._connections.get(str(project_id), set()))


# Singleton used by chat and teacher WS modules
chat_manager = ConnectionManager()
