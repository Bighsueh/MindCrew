"""Canvas action handlers for the ActEngine.

Delegates to the new canvas tools (Phase 14) for spatial-aware operations.
Handles edit_note and delete_note directly via CanvasOps.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from app.chinese.converter import chinese_converter

logger = logging.getLogger(__name__)

# Canvas action types handled by this module
CANVAS_ACTION_TYPES = frozenset({
    "create_note",
    "move_note",
    "edit_note",
    "delete_note",
    "arrange_notes",
    "swap_notes",
    "tidy_area",
})


async def execute_canvas_tool(
    op_type: str,
    action: dict[str, Any],
    project_id: UUID,
    agent_id: str,
    agent_name: str,
) -> None:
    """Dispatch a canvas action to the appropriate tool handler."""
    from app.canvas.tools_manipulation import (
        tool_arrange_notes,
        tool_create_note,
        tool_move_note,
        tool_swap_notes,
        tool_tidy_area,
    )
    from app.bridge.canvas_ops import canvas_ops

    # Update idle timestamp for Rule 5
    await _update_last_event_ts(project_id)

    # Invalidate spatial cache so next perception cycle sees fresh data
    from app.canvas.analyzer import get_spatial_analyzer
    await get_spatial_analyzer().invalidate_full_state_cache(project_id)

    if op_type == "create_note":
        text = _cn(action.get("text", action.get("content", "")))
        color = action.get("color", "yellow")
        position = action.get("position", "region:center")
        result = await tool_create_note(
            project_id=project_id,
            text=text,
            color=color,
            position=position,
            author_id=agent_id,
            author_name=agent_name,
            author_type="ai",
        )
        logger.info(
            "Agent %s create_note project=%s note_id=%s",
            agent_id, project_id, result.get("note_id"),
        )

    elif op_type == "move_note":
        note_id = action.get("note_id", "")
        to = action.get("to", "")
        direction = action.get("direction")
        spacing = action.get("spacing", "default")

        if not to:
            # Fallback: old-style move_note with target_group
            target_group = action.get("target_group")
            if target_group:
                to = f"cluster:{target_group}"
            else:
                logger.warning("move_note: no 'to' or 'target_group' specified")
                return

        result = await tool_move_note(
            project_id=project_id,
            note_id=note_id,
            to=to,
            direction=direction,
            spacing=spacing,
        )
        logger.info(
            "Agent %s move_note project=%s note=%s to=%s ok=%s",
            agent_id, project_id, note_id, to, result.get("success"),
        )

    elif op_type == "edit_note":
        note_id = action.get("note_id", "")
        new_content = _cn(action.get("new_content", action.get("content", "")))
        ok = await canvas_ops.edit_note(
            project_id=project_id,
            note_id=note_id,
            new_content=new_content,
        )
        logger.info(
            "Agent %s edit_note project=%s note=%s ok=%s",
            agent_id, project_id, note_id, ok,
        )

    elif op_type == "delete_note":
        note_id = action.get("note_id", "")
        ok = await canvas_ops.delete_note(
            project_id=project_id,
            note_id=note_id,
        )
        if ok:
            # Invalidate semantic cache on delete
            from app.canvas.analyzer import get_spatial_analyzer
            await get_spatial_analyzer().invalidate_semantic_cache(project_id)
        logger.info(
            "Agent %s delete_note project=%s note=%s ok=%s",
            agent_id, project_id, note_id, ok,
        )

    elif op_type == "arrange_notes":
        note_ids = action.get("note_ids", [])
        layout = action.get("layout", "grid")
        target_region = action.get("target_region", "top-left")
        columns = action.get("columns")
        spacing = action.get("spacing", "default")
        label = _cn(action.get("label", "")) or None
        result = await tool_arrange_notes(
            project_id=project_id,
            note_ids=note_ids,
            layout=layout,
            target_region=target_region,
            columns=columns,
            spacing=spacing,
            label=label,
        )
        # Update last tidy time for ASSESS Rule X
        await _update_last_tidy_ts(project_id)
        logger.info(
            "Agent %s arrange_notes project=%s count=%d layout=%s ok=%s",
            agent_id, project_id, len(note_ids), layout, result.get("success"),
        )

    elif op_type == "swap_notes":
        result = await tool_swap_notes(
            project_id=project_id,
            note_id_a=action.get("note_id_a", ""),
            note_id_b=action.get("note_id_b", ""),
        )
        logger.info(
            "Agent %s swap_notes project=%s ok=%s",
            agent_id, project_id, result.get("success"),
        )

    elif op_type == "tidy_area":
        scope = action.get("scope", "all")
        target = action.get("target")
        strategy = action.get("strategy", "align_grid")
        result = await tool_tidy_area(
            project_id=project_id,
            scope=scope,
            target=target,
            strategy=strategy,
        )
        await _update_last_tidy_ts(project_id)
        logger.info(
            "Agent %s tidy_area project=%s scope=%s strategy=%s ok=%s",
            agent_id, project_id, scope, strategy, result.get("success"),
        )

    else:
        logger.warning("Unknown canvas op type: %s", op_type)


def _cn(text: str) -> str:
    """Apply Chinese conversion if non-empty."""
    if not text:
        return text
    try:
        return chinese_converter.convert(text)
    except Exception:
        return text


async def _update_last_event_ts(project_id: UUID) -> None:
    """Update project's last-event timestamp in Redis."""
    try:
        import redis.asyncio as aioredis
        from app.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.set(f"project:{project_id}:last_event_ts", str(time.time()))
        await r.aclose()
    except Exception:
        pass


async def _update_last_tidy_ts(project_id: UUID) -> None:
    """Update project's last-tidy timestamp for ASSESS Rule X."""
    try:
        import redis.asyncio as aioredis
        from app.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.set(f"project:{project_id}:last_tidy_ts", str(time.time()))
        await r.aclose()
    except Exception:
        pass
