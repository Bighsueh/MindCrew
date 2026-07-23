"""In-memory canvas state manager per project.

Provides thread-safe (asyncio.Lock) per-project canvas state storage.
This is a simplified implementation that can be swapped for real Yjs/yrs later.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass
class NoteData:
    note_id: str
    content: str
    position_x: float
    position_y: float
    color: str
    author_id: str
    author_name: str
    author_type: str  # "ai" or "human"
    group_name: str | None = None
    # Spec 27 (Phase 36) §10：接話式便條欄位。
    # 注意 group_id（語意主題群，顧客/店員…）與 group_name（既有空間 group）並存、不混用。
    kind: str = "content"            # "content" | "label"
    group_id: str | None = None      # 所屬主題群（同對象聚一起）
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.note_id,
            "content": self.content,
            "position": {"x": self.position_x, "y": self.position_y},
            "color": self.color,
            "author": f"{self.author_name}({self.author_type})",
            "author_id": self.author_id,
            "group_name": self.group_name,
            # Spec 27 欄位
            "kind": self.kind,
            "group_id": self.group_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class CanvasState:
    notes: dict[str, NoteData] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def get_canvas_dict(self) -> dict[str, Any]:
        """Return canvas state in the spec §2.1 canvas_state format."""
        notes_list = [n.to_dict() for n in self.notes.values()]
        groups_map: dict[str, list[str]] = {}
        ungrouped: list[str] = []

        for note in self.notes.values():
            if note.group_name:
                groups_map.setdefault(note.group_name, []).append(note.note_id)
            else:
                ungrouped.append(note.note_id)

        groups = [{"name": k, "notes": v} for k, v in groups_map.items()]
        return {
            "total_notes": len(self.notes),
            "groups": groups,
            "ungrouped": ungrouped,
            "notes": notes_list,
        }


class CanvasStateManager:
    """Singleton manager for per-project canvas states."""

    def __init__(self) -> None:
        self._states: dict[UUID, CanvasState] = {}
        self._global_lock = asyncio.Lock()

    async def get_or_create(self, project_id: UUID) -> CanvasState:
        """Get existing canvas state or create a new one."""
        async with self._global_lock:
            if project_id not in self._states:
                self._states[project_id] = CanvasState()
                logger.debug("Created canvas state for project %s", project_id)
            return self._states[project_id]

    async def remove_project(self, project_id: UUID) -> None:
        """Remove canvas state for a project (e.g. on project deletion)."""
        async with self._global_lock:
            self._states.pop(project_id, None)


# Singleton instance
canvas_state_manager = CanvasStateManager()
