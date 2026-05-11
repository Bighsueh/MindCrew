"""Deliverable-required check before sub_phase advancement (Spec 14 A9).

每個 sub_phase 推進前，先查 deliverables_required 列表，
確認每張要求的便條（zone + count + template + color）都存在。

被 advance_sub_phase 在執行前呼叫。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.canvas.zone_registry import get_all_zones_for_project
from app.canvas.zones import resolve_zone_by_position
from app.canvas.text_templates import validate_template
from app.stages.sub_phases import SUB_PHASES, DeliverableRequirement

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliverableCheckResult:
    passed: bool
    missing: list[str]               # 中文錯誤訊息列表
    found_counts: dict[str, int]     # zone_id → count


async def check_deliverables(
    project_id: UUID,
    sub_phase_id: str,
) -> DeliverableCheckResult:
    """檢查當前 sub-phase 的 deliverables 是否都達成。"""
    sp = SUB_PHASES.get(sub_phase_id)
    if sp is None or not sp.deliverables_required:
        return DeliverableCheckResult(passed=True, missing=[], found_counts={})

    # Load canvas notes
    try:
        from app.canvas.analyzer import get_spatial_analyzer
        analyzer = get_spatial_analyzer()
        analysis = await analyzer.analyze(project_id)
        notes = analysis.notes
    except Exception as exc:
        # Canvas 不可達時保守 pass（避免擋住流程）
        logger.warning("deliverable check: canvas analysis failed: %s — pass", exc)
        return DeliverableCheckResult(passed=True, missing=[], found_counts={})

    project_bounds = await get_all_zones_for_project(project_id)

    missing: list[str] = []
    found_counts: dict[str, int] = {}
    for req in sp.deliverables_required:
        count = await _count_matching_notes(
            notes, req, sub_phase_id, project_bounds,
        )
        found_counts[req.zone_id] = count
        if count < req.min_count:
            extra = f"（目前 {count} / 需要 {req.min_count}）"
            msg = req.description_zh + extra
            missing.append(msg)

    return DeliverableCheckResult(
        passed=len(missing) == 0,
        missing=missing,
        found_counts=found_counts,
    )


async def _count_matching_notes(
    notes: list[Any],
    req: DeliverableRequirement,
    sub_phase_id: str,
    project_bounds: dict,
) -> int:
    count = 0
    for note in notes:
        # Color filter
        if req.color and getattr(note, "color", None) != req.color:
            continue
        # Zone filter
        zone = resolve_zone_by_position(
            note.x, note.y, sub_phase_id,
            project_zone_bounds=project_bounds,
        )
        if zone is None or zone.id != req.zone_id:
            continue
        # Template filter
        if req.template_id:
            text = getattr(note, "content", "") or getattr(note, "text", "")
            tpl_result = validate_template(text, req.template_id)
            if not tpl_result.passed:
                continue
        count += 1
    return count
