"""Canvas manipulation tools for AI agents.

These tools translate high-level intents into coordinate operations:
  move_note, arrange_notes, create_note, swap_notes, tidy_area, draw_zone

Spec 13 — create_note 整合 zone resolution + content gate + template validation。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.bridge.canvas_ops import canvas_ops
from app.canvas.analyzer import get_spatial_analyzer
from app.canvas.content_gate import check_text, check_text_with_llm
from app.canvas.layout_engine import CoordinateUpdate, get_layout_engine
from app.canvas.text_templates import validate_template, validate_template_with_canvas
from app.canvas.zone_registry import (
    get_all_zones_for_project,
    get_zone_bounds,
    register_zone,
)
from app.canvas.zones import (
    Bounds,
    Zone,
    ZONES,
    get_active_zones,
    get_zone,
    resolve_zone_by_position,
    zone_allows_color,
)
from app.chinese.converter import chinese_converter
from app.stages.sub_phases import SUB_PHASES, get_sub_phase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateRejection:
    """Represents a rejection from any gate (zone / color / content / template)."""

    reason_zh: str
    rule_module: str
    rule_name: str
    matched_text: str | None = None


@dataclass(frozen=True)
class CreateNoteOutcome:
    """Outcome of a gated create_note call."""

    success: bool
    note_id: str | None = None
    x: float | None = None
    y: float | None = None
    rejection: GateRejection | None = None
    zone_id: str | None = None
    gate_violation_metadata: dict[str, Any] | None = None


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
    sub_phase_id: str | None = None,
    force_publish: bool = False,
) -> dict[str, Any]:
    """Create a new note at a semantic position with Spec 13 zone + gate checks.

    Args:
      sub_phase_id: 當前 sub-phase。若 None 則跳過所有 zone/gate 檢查（向下相容）
      force_publish: 人類使用者強制送出（違反 gate 但仍 publish，標記 gate_violation）。
        AI agent 不應啟用此 flag。

    Returns dict with: success, note_id, x, y, [rejection], [zone_id], [gate_violation]
    """
    converted_text = chinese_converter.convert(text)

    analyzer = get_spatial_analyzer()
    analysis = await analyzer.analyze(project_id)
    engine = get_layout_engine()

    x, y = engine.resolve_position(
        to=position,
        notes=analysis.notes,
        clusters=analysis.cluster_state.clusters,
    )

    # 若 sub_phase 提供 → 跑 Spec 13 gates
    outcome = await _evaluate_create_gates(
        project_id=project_id,
        text=converted_text,
        color=color,
        x=x,
        y=y,
        sub_phase_id=sub_phase_id,
        author_type=author_type,
        force_publish=force_publish,
    )
    if outcome.rejection is not None and not outcome.gate_violation_metadata:
        # Hard reject
        return {
            "success": False,
            "rejection": {
                "reason_zh": outcome.rejection.reason_zh,
                "rule_module": outcome.rejection.rule_module,
                "rule_name": outcome.rejection.rule_name,
                "matched_text": outcome.rejection.matched_text,
            },
        }

    note_id = await canvas_ops.add_note(
        project_id=project_id,
        content=converted_text,
        position={"x": x, "y": y},
        color=color,
        author_id=author_id,
        author_name=author_name,
        author_type=author_type,
    )

    # 紀錄 gate_violation metadata（人類強制送出時）
    if outcome.gate_violation_metadata:
        try:
            await canvas_ops.set_note_metadata(  # type: ignore[attr-defined]
                project_id=project_id,
                note_id=note_id,
                metadata={"gate_violation": outcome.gate_violation_metadata},
            )
        except AttributeError:
            # canvas_ops 未實作 set_note_metadata，先記錄日誌
            logger.warning(
                "gate_violation metadata not persisted (canvas_ops.set_note_metadata missing): "
                "project=%s note=%s violation=%s",
                project_id, note_id, outcome.gate_violation_metadata,
            )

    await analyzer.invalidate_semantic_cache(project_id)

    result: dict[str, Any] = {
        "success": True,
        "note_id": note_id,
        "x": x,
        "y": y,
    }
    if outcome.zone_id:
        result["zone_id"] = outcome.zone_id
    if outcome.gate_violation_metadata:
        result["gate_violation"] = outcome.gate_violation_metadata
    return result


async def _evaluate_create_gates(
    project_id: UUID,
    text: str,
    color: str,
    x: float,
    y: float,
    sub_phase_id: str | None,
    author_type: str,
    force_publish: bool,
) -> CreateNoteOutcome:
    """Run zone / color / content gate / template checks.

    AI 違規 → hard reject（gate_violation_metadata = None, rejection 有值）
    人類 + force_publish=True → publish but 標記 gate_violation
    人類 + force_publish=False → hard reject
    sub_phase_id=None → 直接 pass（向下相容）
    """
    if sub_phase_id is None:
        return CreateNoteOutcome(success=True)

    try:
        sub_phase = get_sub_phase(sub_phase_id)
    except KeyError:
        logger.warning("Unknown sub_phase %s in create_note; skip gates", sub_phase_id)
        return CreateNoteOutcome(success=True)

    # Step 1: Resolve zone
    project_bounds = await get_all_zones_for_project(project_id)
    zone = resolve_zone_by_position(x, y, sub_phase_id, project_zone_bounds=project_bounds)
    if zone is None:
        return CreateNoteOutcome(
            success=False,
            rejection=GateRejection(
                reason_zh="此座標未落在任何已定義的區域內，請貼到有 dashed 框的區域裡。",
                rule_module="zone_resolution",
                rule_name="no_active_zone",
            ),
        )

    # Step 2: phase_visible 已由 get_active_zones 過濾，再次確認
    if sub_phase_id not in zone.phase_visible and zone.id != "park":
        return CreateNoteOutcome(
            success=False,
            rejection=GateRejection(
                reason_zh=f"區域「{zone.id}」於本階段不開放寫入。",
                rule_module="zone_resolution",
                rule_name="zone_not_visible",
            ),
        )

    # Step 3: Color check
    if not zone_allows_color(zone, color):
        return CreateNoteOutcome(
            success=False,
            rejection=GateRejection(
                reason_zh=f"區域「{zone.id}」只接受顏色：{', '.join(zone.allowed_colors)}。",
                rule_module="zone_color",
                rule_name="color_not_allowed",
            ),
        )

    # Step 4: Content gate
    # Park 區跳過 content gate（孤兒收容所），其他套用 zone + sub_phase 合併規則
    if zone.id != "park":
        all_modules = tuple(set(zone.gate_modules) | set(sub_phase.gate_modules))
        # Spec 14: 使用 LLM-judged 兩層評估（regex 預過濾 + LLM 確認，能識別引述/否定/Meta）
        gate_result = await check_text_with_llm(
            text,
            all_modules,
            context={"sub_phase": sub_phase_id, "zone": zone.id},
            project_id=project_id,
        )
        if not gate_result.passed:
            violation_metadata = None
            if author_type == "human" and force_publish:
                # Human override allowed
                violation_metadata = {
                    "phase": sub_phase_id,
                    "zone_id": zone.id,
                    "rule": gate_result.violated_rule,
                    "module": gate_result.violated_module,
                    "matched_text": gate_result.matched_text,
                }
            return CreateNoteOutcome(
                success=False,
                zone_id=zone.id,
                rejection=GateRejection(
                    reason_zh=gate_result.message_zh or "違反語言規則",
                    rule_module=gate_result.violated_module or "unknown",
                    rule_name=gate_result.violated_rule or "unknown",
                    matched_text=gate_result.matched_text,
                ),
                gate_violation_metadata=violation_metadata,
            )

    # Step 5: Template check (only if zone has a template requirement and text non-empty)
    if zone.templates:
        for template_id in zone.templates:
            # Spec 14 N4: 使用 canvas-aware 版本驗證 cite id 存在性
            tpl_result = await validate_template_with_canvas(text, template_id, project_id)
            if not tpl_result.passed:
                violation_metadata = None
                if author_type == "human" and force_publish:
                    violation_metadata = {
                        "phase": sub_phase_id,
                        "zone_id": zone.id,
                        "rule": "template_mismatch",
                        "module": f"template:{template_id}",
                        "matched_text": None,
                    }
                return CreateNoteOutcome(
                    success=False,
                    zone_id=zone.id,
                    rejection=GateRejection(
                        reason_zh=tpl_result.reason_zh or "格式不符",
                        rule_module=f"template:{template_id}",
                        rule_name="template_mismatch",
                    ),
                    gate_violation_metadata=violation_metadata,
                )

    return CreateNoteOutcome(success=True, zone_id=zone.id)


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


# Spec 13: zone drawing tools now live in `app.canvas.tools_zones`
from app.canvas.tools_zones import tool_draw_zone, tool_draw_template  # noqa: E402, F401


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
