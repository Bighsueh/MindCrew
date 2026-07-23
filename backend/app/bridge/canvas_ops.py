"""Canvas operations via Yjs sidecar HTTP API.

All operations call the Node.js sidecar which manages the Yjs CRDT docs.
Browser clients sync via y-websocket directly with the sidecar.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.SIDECAR_URL,
            timeout=10.0,
        )
    return _client


class CanvasOps:
    """Canvas operations facade backed by the Yjs sidecar."""

    async def _invalidate_spatial_cache(self, project_id: UUID) -> None:
        """寫入成功後讓空間 full-state 快取失效（Phase 42 D1d Bug①）。

        ``analyzer.get_full_state`` 有 3s Redis 快取（降 sidecar 讀負載）。canvas_ops
        直接寫 sidecar 的呼叫端（force_close 搬便條、動畫 stagger、兜底補便條…）繞過
        ``act_canvas`` 的失效點，會讓下一次感知/閘檢查讀到搬移前舊快照——live 2026-06-15
        坐實：force_close 搬 PS 後 2.7 配對閘 3s 內看不到選定 PS → 永遠 thrash。
        讓「寫入路徑自己 bust 快取」＝讀後寫一致性。best-effort（不影響主流程）；
        lazy import 避免與 analyzer（經 sections 間接）循環匯入。
        """
        try:
            from app.canvas.analyzer import get_spatial_analyzer

            await get_spatial_analyzer().invalidate_full_state_cache(project_id)
        except Exception:
            logger.debug(
                "invalidate spatial cache failed project=%s", project_id, exc_info=True
            )

    async def add_note(
        self,
        project_id: UUID,
        content: str,
        position: str | dict[str, float] | None = None,
        color: str = "yellow",
        author_id: str = "system",
        author_name: str = "System",
        author_type: str = "ai",
        created_at: str | None = None,
        *,
        kind: str = "content",
        group_id: str | None = None,
        cites: list[str] | None = None,
        time_box_forced: bool = False,
    ) -> str:
        """Add a note. Returns the new note_id.

        Phase 24.A: 若提供 created_at（ISO Z 字串），sidecar 會用該時間覆蓋自動生成值，
        讓 Activity Highlight 的時間配對在 AI 建立的便利貼上也成立。

        Spec 27 (Phase 36): kind（content/label）/ group_id（主題群）原樣透傳給 sidecar NoteShape。
        Spec 06 v4.25 (Phase 42 C0): cites（引用鏈，sidecar 會過濾不存在 id）/
        time_box_forced（C2 time-box 強推標記；人類與 crew 路徑不可寫）。
        """
        client = _get_client()
        author = f"{author_name}({author_type})"
        body: dict[str, Any] = {
            "content": content,
            "author": author,
            "color": color,
        }
        if position is not None:
            body["position"] = position
        if created_at is not None:
            body["createdAt"] = created_at
        # Spec 27 欄位：只在非預設時帶上，保持向下相容
        if kind and kind != "content":
            body["kind"] = kind
        if group_id is not None:
            body["group_id"] = group_id
        # Spec 06 v4.25 (Phase 42 C0)：非預設才帶
        if cites:
            body["cites"] = cites
        if time_box_forced:
            body["time_box_forced"] = True

        resp = await client.post(
            f"/api/projects/{project_id}/notes", json=body
        )
        resp.raise_for_status()
        data = resp.json()
        note_id = data["id"]
        logger.info("Canvas add_note project=%s note_id=%s", project_id, note_id)
        await self._invalidate_spatial_cache(project_id)
        return note_id

    async def move_note(
        self,
        project_id: UUID,
        note_id: str,
        target_group: str | None,
    ) -> bool:
        """Move a note to a group. Returns success."""
        if not target_group:
            return False
        client = _get_client()
        resp = await client.post(
            f"/api/projects/{project_id}/notes/{note_id}/move",
            json={"target_group": target_group},
        )
        if resp.status_code == 404:
            logger.warning("move_note: note %s not found", note_id)
            return False
        resp.raise_for_status()
        await self._invalidate_spatial_cache(project_id)
        return True

    async def edit_note(
        self,
        project_id: UUID,
        note_id: str,
        new_content: str,
    ) -> bool:
        """Edit a note's content. Returns success."""
        client = _get_client()
        resp = await client.patch(
            f"/api/projects/{project_id}/notes/{note_id}",
            json={"content": new_content},
        )
        if resp.status_code == 404:
            logger.warning("edit_note: note %s not found", note_id)
            return False
        resp.raise_for_status()
        await self._invalidate_spatial_cache(project_id)
        return True

    async def update_note_group_id(
        self,
        project_id: UUID,
        note_id: str,
        group_id: str | None,
    ) -> bool:
        """Update a note's semantic concept group_id. Returns success."""
        client = _get_client()
        resp = await client.patch(
            f"/api/projects/{project_id}/notes/{note_id}/group",
            json={"group_id": group_id},
        )
        if resp.status_code == 404:
            logger.warning("update_note_group_id: note %s not found", note_id)
            return False
        resp.raise_for_status()
        await self._invalidate_spatial_cache(project_id)
        return True

    async def update_note_cites(
        self,
        project_id: UUID,
        note_id: str,
        cites: list[str],
    ) -> bool:
        """全量覆蓋便條引用鏈（Spec 06 v4.25, Phase 42 C0）。Returns success."""
        client = _get_client()
        resp = await client.patch(
            f"/api/projects/{project_id}/notes/{note_id}/cites",
            json={"cites": cites},
        )
        if resp.status_code == 404:
            logger.warning("update_note_cites: note %s not found", note_id)
            return False
        resp.raise_for_status()
        await self._invalidate_spatial_cache(project_id)
        return True

    async def set_note_metadata(
        self,
        project_id: UUID,
        note_id: str,
        metadata: dict[str, Any],
    ) -> bool:
        """合併便條 metadata（gate_violation 標記，Spec 13 §7.1）。Returns success."""
        client = _get_client()
        resp = await client.patch(
            f"/api/projects/{project_id}/notes/{note_id}/metadata",
            json={"metadata": metadata},
        )
        if resp.status_code == 404:
            logger.warning("set_note_metadata: note %s not found", note_id)
            return False
        resp.raise_for_status()
        await self._invalidate_spatial_cache(project_id)
        return True

    async def get_move_events(
        self, project_id: UUID, since: int = 0
    ) -> dict[str, Any]:
        """拉取 move-delta 可讀事件（Spec 10 v2.0 §4.7）。失敗回空（cursor 不前進）。"""
        client = _get_client()
        try:
            resp = await client.get(
                f"/api/projects/{project_id}/move-events", params={"since": since}
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_move_events failed: %s", exc)
            return {"events": [], "latest_seq": since}

    async def delete_note(self, project_id: UUID, note_id: str) -> bool:
        """Delete a note. Returns success."""
        client = _get_client()
        resp = await client.delete(
            f"/api/projects/{project_id}/notes/{note_id}"
        )
        if resp.status_code == 404:
            logger.warning("delete_note: note %s not found", note_id)
            return False
        resp.raise_for_status()
        await self._invalidate_spatial_cache(project_id)
        return True

    async def get_canvas_state_full(self, project_id: UUID) -> list[dict[str, Any]]:
        """Get full geometry for all shapes from sidecar."""
        client = _get_client()
        try:
            resp = await client.get(f"/api/projects/{project_id}/canvas-state/full")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_canvas_state_full failed: %s", exc)
            return []

    async def batch_update_coordinates(
        self,
        project_id: UUID,
        updates: list[dict[str, Any]],
        moved_by: str | None = None,
    ) -> bool:
        """Batch-update note coordinates via sidecar (atomic Yjs transaction).

        Spec 10 v2.0 §4.7：moved_by 進 Yjs transaction origin，供 move-delta 事件歸因。
        """
        if not updates:
            return True
        client = _get_client()
        body: dict[str, Any] = {"updates": updates}
        if moved_by:
            body["moved_by"] = moved_by
        try:
            resp = await client.post(
                f"/api/projects/{project_id}/batch-update-coordinates",
                json=body,
            )
            if resp.status_code == 404:
                logger.warning("batch_update_coordinates: notes not found")
                return False
            resp.raise_for_status()
            await self._invalidate_spatial_cache(project_id)
            return True
        except Exception as exc:
            logger.warning("batch_update_coordinates failed: %s", exc)
            return False

    async def staggered_update_coordinates(
        self,
        project_id: UUID,
        updates: list[dict[str, Any]],
        stagger_ms: int = 400,
        moving_by: str | None = None,
    ) -> bool:
        """Update note coordinates one-by-one with stagger delays.

        The sidecar applies each update in its own Yjs transaction with
        setTimeout delays, creating a sequential animation effect on the
        frontend. If moving_by is provided, sets a _moving_by metadata field
        on each note during movement for visual lock indication.

        Phase 42 D1b (spec 12 §3.3 v4.1)：同批 stagger 下限 400ms——低於此使用者
        看不出「動的是哪幾張」。預設由舊 150 上修為 400；<400 一律夾到下限。
        """
        if not updates:
            return True
        if stagger_ms < 400:
            logger.debug(
                "stagger_ms=%d < 400 floor; clamping to 400 (spec 12 §3.3)", stagger_ms
            )
            stagger_ms = 400
        client = _get_client()
        payload: dict[str, Any] = {
            "updates": updates,
            "stagger_ms": stagger_ms,
        }
        if moving_by:
            payload["moving_by"] = moving_by
        try:
            resp = await client.post(
                f"/api/projects/{project_id}/staggered-update-coordinates",
                json=payload,
            )
            resp.raise_for_status()
            await self._invalidate_spatial_cache(project_id)
            return True
        except Exception as exc:
            logger.warning("staggered_update_coordinates failed: %s", exc)
            return False

    async def get_canvas_state(self, project_id: UUID) -> dict[str, Any]:
        """Get canvas state from sidecar (spec §2.1 format)."""
        client = _get_client()
        try:
            resp = await client.get(f"/api/projects/{project_id}/state")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("get_canvas_state failed: %s", exc)
            return {
                "total_notes": 0,
                "groups": [],
                "ungrouped": [],
                "notes": [],
            }


canvas_ops = CanvasOps()
