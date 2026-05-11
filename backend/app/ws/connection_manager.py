from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """管理依 project_id 分組的 WebSocket 連線。

    Phase 20 / spec 13-personal-chat §6.2：為了讓 forwarder 能依
    ``viewer_user_id`` 做 RBAC 過濾，新增「ws → user_id」對照表。
    既有 caller 仍可只傳 ``project_id, ws``（向下相容）；新 caller
    應傳入 ``user_id`` 以啟用個人聊天路由。
    """

    def __init__(self) -> None:
        # project_id (str) → set of WebSocket
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        # ws → user_id 字串；若 caller 未提供則不存在於此 dict
        self._ws_user: dict[WebSocket, str] = {}

    def connect(
        self,
        project_id: UUID,
        ws: WebSocket,
        user_id: str | UUID | None = None,
    ) -> None:
        """註冊一條 WebSocket 連線。

        Args:
            project_id: 該連線所屬的 project。
            ws: WebSocket 物件。
            user_id: 連線所屬的 user（personal chat RBAC 必備）。
                若 ``None`` 表示舊路徑或匿名（forwarder 將視同 group-only viewer）。
        """
        key = str(project_id)
        self._connections[key].add(ws)
        if user_id is not None:
            self._ws_user[ws] = str(user_id)
        logger.debug(
            "WS connected project=%s user=%s total=%d",
            key,
            user_id,
            len(self._connections[key]),
        )

    def disconnect(self, project_id: UUID, ws: WebSocket) -> None:
        key = str(project_id)
        self._connections[key].discard(ws)
        if not self._connections[key]:
            del self._connections[key]
        # 移除 user 對照（若有）。
        self._ws_user.pop(ws, None)
        logger.debug("WS disconnected project=%s", key)

    def get_user_id(self, ws: WebSocket) -> str | None:
        """取回該 ws 連線對應的 user_id（forwarder RBAC 用）。

        Returns:
            連線時提供的 user_id 字串；若無則 ``None``。
        """
        return self._ws_user.get(ws)

    async def broadcast(self, project_id: UUID, message: dict) -> None:
        """把 dict 廣播給該 project 下所有連線。"""
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
