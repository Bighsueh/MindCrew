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

    async def add_note(
        self,
        project_id: UUID,
        content: str,
        position: str | dict[str, float] | None = None,
        color: str = "yellow",
        author_id: str = "system",
        author_name: str = "System",
        author_type: str = "ai",
    ) -> str:
        """Add a note. Returns the new note_id."""
        client = _get_client()
        author = f"{author_name}({author_type})"
        body: dict[str, Any] = {
            "content": content,
            "author": author,
            "color": color,
        }
        if position is not None:
            body["position"] = position

        resp = await client.post(
            f"/api/projects/{project_id}/notes", json=body
        )
        resp.raise_for_status()
        data = resp.json()
        note_id = data["id"]
        logger.info("Canvas add_note project=%s note_id=%s", project_id, note_id)
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
        return True

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
    ) -> bool:
        """Batch-update note coordinates via sidecar (atomic Yjs transaction)."""
        if not updates:
            return True
        client = _get_client()
        try:
            resp = await client.post(
                f"/api/projects/{project_id}/batch-update-coordinates",
                json={"updates": updates},
            )
            if resp.status_code == 404:
                logger.warning("batch_update_coordinates: notes not found")
                return False
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("batch_update_coordinates failed: %s", exc)
            return False

    async def staggered_update_coordinates(
        self,
        project_id: UUID,
        updates: list[dict[str, Any]],
        stagger_ms: int = 150,
        moving_by: str | None = None,
    ) -> bool:
        """Update note coordinates one-by-one with stagger delays.

        The sidecar applies each update in its own Yjs transaction with
        setTimeout delays, creating a sequential animation effect on the
        frontend. If moving_by is provided, sets a _moving_by metadata field
        on each note during movement for visual lock indication.
        """
        if not updates:
            return True
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
