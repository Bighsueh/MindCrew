"""Canvas manipulation tools for AI agents.

These tools translate high-level intents into coordinate operations:
  move_note, arrange_notes, create_note, swap_notes, tidy_area
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.bridge.canvas_ops import canvas_ops
from app.canvas.analyzer import get_spatial_analyzer
from app.canvas.layout_engine import CoordinateUpdate, get_layout_engine
from app.chinese.converter import chinese_converter

logger = logging.getLogger(__name__)


async def tool_move_note(
    project_id: UUID,
    note_id: str,
    to: str,
    direction: str | None = None,
    spacing: str = "default",
) -> dict[str, Any]:
    """Move a single note to a semantic destination."""
    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)
    engine = get_layout_engine()

    x, y = engine.resolve_position(
        to=to,
        notes=analysis.notes,
        clusters=analysis.cluster_state.clusters,
        direction=direction,
        spacing=spacing,
    )

    ok = await canvas_ops.batch_update_coordinates(
        project_id,
        [{"id": note_id, "x": x, "y": y}],
    )

    return {"success": ok, "note_id": note_id, "x": x, "y": y}


async def tool_arrange_notes(
    project_id: UUID,
    note_ids: list[str],
    layout: str,
    target_region: str,
    columns: int | None = None,
    spacing: str = "default",
    label: str | None = None,
) -> dict[str, Any]:
    """Batch-arrange notes in a layout pattern."""
    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)
    engine = get_layout_engine()

    updates = engine.compute_arrangement(
        note_ids=note_ids,
        layout=layout,
        target_region=target_region,
        notes=analysis.notes,
        columns=columns,
        spacing=spacing,
    )

    ok = await canvas_ops.batch_update_coordinates(
        project_id,
        [{"id": u.id, "x": u.x, "y": u.y} for u in updates],
    )

    result: dict[str, Any] = {
        "success": ok,
        "arranged_count": len(updates),
        "layout": layout,
    }

    # Create a label note above the arrangement if requested
    if label and ok and updates:
        converted_label = chinese_converter.convert(label)
        min_x = min(u.x for u in updates)
        min_y = min(u.y for u in updates)
        label_note_id = await canvas_ops.add_note(
            project_id=project_id,
            content=converted_label,
            position={"x": min_x, "y": min_y - 160},
            color="blue",
            author_id="system",
            author_name="System",
            author_type="ai",
        )
        result["label_note_id"] = label_note_id
        await analyzer.invalidate_semantic_cache(project_id)

    return result


async def tool_create_note(
    project_id: UUID,
    text: str,
    color: str = "yellow",
    position: str = "region:center",
    author_id: str = "system",
    author_name: str = "System",
    author_type: str = "ai",
) -> dict[str, Any]:
    """Create a new note at a semantic position."""
    converted_text = chinese_converter.convert(text)

    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)
    engine = get_layout_engine()

    x, y = engine.resolve_position(
        to=position,
        notes=analysis.notes,
        clusters=analysis.cluster_state.clusters,
    )

    note_id = await canvas_ops.add_note(
        project_id=project_id,
        content=converted_text,
        position={"x": x, "y": y},
        color=color,
        author_id=author_id,
        author_name=author_name,
        author_type=author_type,
    )

    # Invalidate semantic cache (new note changes clusters)
    await analyzer.invalidate_semantic_cache(project_id)

    return {"success": True, "note_id": note_id, "x": x, "y": y}


async def tool_swap_notes(
    project_id: UUID,
    note_id_a: str,
    note_id_b: str,
) -> dict[str, Any]:
    """Swap the positions of two notes."""
    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)

    note_a = next((n for n in analysis.notes if n.id == note_id_a), None)
    note_b = next((n for n in analysis.notes if n.id == note_id_b), None)

    if not note_a or not note_b:
        return {"success": False, "error": "One or both notes not found"}

    ok = await canvas_ops.batch_update_coordinates(
        project_id,
        [
            {"id": note_id_a, "x": note_b.x, "y": note_b.y},
            {"id": note_id_b, "x": note_a.x, "y": note_a.y},
        ],
    )

    return {"success": ok, "swapped": [note_id_a, note_id_b]}


async def tool_tidy_area(
    project_id: UUID,
    scope: str,
    target: str | None = None,
    strategy: str = "align_grid",
) -> dict[str, Any]:
    """Tidy a scope of the canvas."""
    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)
    engine = get_layout_engine()

    updates = engine.compute_tidy(
        scope=scope,
        target=target,
        strategy=strategy,
        notes=analysis.notes,
        clusters=analysis.cluster_state.clusters,
    )

    if not updates:
        return {"success": True, "tidied_count": 0}

    ok = await canvas_ops.batch_update_coordinates(
        project_id,
        [{"id": u.id, "x": u.x, "y": u.y} for u in updates],
    )

    return {"success": ok, "tidied_count": len(updates), "strategy": strategy}


# ── Phase 2 Stubs ──


async def tool_create_arrow(
    project_id: UUID,
    from_note_id: str,
    to_note_id: str,
    label: str | None = None,
) -> dict[str, Any]:
    """Phase 2: Create an arrow between two notes."""
    raise NotImplementedError("Phase 2: create_arrow not yet implemented")


async def tool_create_frame(
    project_id: UUID,
    note_ids: list[str],
    title: str | None = None,
) -> dict[str, Any]:
    """Phase 2: Create a frame grouping notes."""
    raise NotImplementedError("Phase 2: create_frame not yet implemented")
