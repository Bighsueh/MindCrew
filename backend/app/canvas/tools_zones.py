"""Zone drawing tools — Spec 13 §2.2.

Supervisor-only tools: 在白板上畫出 zone 視覺框並註冊 bounds。
從 tools_manipulation.py 抽出以維持 ≤ 500 行檔案上限。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.bridge.canvas_ops import canvas_ops
from app.canvas.zone_registry import register_zone
from app.canvas.zones import Bounds, ZONES
from app.chinese.converter import chinese_converter

logger = logging.getLogger(__name__)


async def tool_open_section(
    project_id: UUID,
    title: str,
    author_id: str = "system",
    author_name: str = "System",
) -> dict[str, Any]:
    """Supervisor-only：動態往下開新 section（spec 10 v2.0 §5.9，Phase 42 C0）。

    流程：
      1. 硬計算 bounds——最下方既有 zone / section / 便條 extent 之下開全寬帶
      2. 寫入動態 section registry（Redis）
      3. 帶頭自動貼一張 kind=label 標題便條（過 OpenCC 繁中轉換）
      4. 不畫 dashed 框（C0 裁定 4：標題便條＝視覺錨點；D1 觀察待辦）

    話術義務（口頭說明新區用途）由 prompt 層承擔（D1 §7.3），不在本工具內。
    Returns: { success, section_id, bounds, title_note_id }
    """
    from app.canvas.sections import (
        compute_open_section_bounds,
        list_sections,
        register_section,
    )

    title = (title or "").strip()
    if not title:
        return {"success": False, "error": "title is required"}

    converted_title = chinese_converter.convert(title)

    # 冪等（spec 10 §5.9）：同標題選定 section 已存在 → 回既有、不重開（避免雙選定區
    # 造成 2.6→2.7 選定交接的搬入目標與 union 讀取分歧）。
    existing = [
        s for s in await list_sections(project_id)
        if s.get("title") == converted_title
    ]
    if existing:
        sec = existing[0]
        logger.info(
            "open_section: reuse existing project=%s section=%s title=%s (idempotent)",
            project_id, sec["id"], converted_title,
        )
        return {
            "success": True,
            "section_id": sec["id"],
            "bounds": {"x": sec["x"], "y": sec["y"], "w": sec["w"], "h": sec["h"]},
            "title_note_id": None,
            "reused": True,
        }

    bounds, order = await compute_open_section_bounds(project_id)
    section = await register_section(project_id, converted_title, bounds, order)

    title_note_id: str | None = None
    try:
        title_note_id = await canvas_ops.add_note(
            project_id=project_id,
            content=converted_title,
            position={"x": bounds.x + 8, "y": bounds.y + 8},
            color="pink",
            author_id=author_id,
            author_name=author_name,
            author_type="ai",
            kind="label",
        )
    except Exception as exc:
        logger.warning("open_section: title sticky creation failed: %s", exc)

    logger.info(
        "Agent %s open_section project=%s section=%s title=%s bounds=(%s,%s,%s,%s)",
        author_id, project_id, section["id"], converted_title,
        bounds.x, bounds.y, bounds.w, bounds.h,
    )

    return {
        "success": True,
        "section_id": section["id"],
        "bounds": {
            "x": bounds.x, "y": bounds.y, "w": bounds.w, "h": bounds.h,
        },
        "title_note_id": title_note_id,
    }


async def tool_draw_zone(
    project_id: UUID,
    zone_id: str,
    bounds: dict[str, float] | None = None,
    author_id: str = "system",
    author_name: str = "System",
) -> dict[str, Any]:
    """Supervisor-only: 畫出一個 zone 的視覺框 + Pink 標題便條，並註冊 bounds。

    流程：
      1. 取 Zone definition（default bounds, visual）
      2. 若呼叫端有給 bounds，覆寫 default
      3. 寫入 zone_registry（Redis）
      4. 建立 Pink 標題便條於左上角
      5. 廣播給前端繪製 dashed 外框（事件 zone:drawn）

    Returns: { success, zone_id, bounds, title_note_id }
    """
    if zone_id not in ZONES:
        return {"success": False, "error": f"Unknown zone_id: {zone_id}"}

    zone = ZONES[zone_id]
    final_bounds: Bounds
    if bounds:
        final_bounds = Bounds(
            x=float(bounds.get("x", 0)),
            y=float(bounds.get("y", 0)),
            w=float(bounds.get("w", 600)),
            h=float(bounds.get("h", 400)),
        )
    elif zone.default_bounds:
        final_bounds = zone.default_bounds
    else:
        return {
            "success": False,
            "error": f"Zone {zone_id} has no default bounds; must specify",
        }

    # 1. Register
    await register_zone(project_id, zone_id, final_bounds)

    # 2. Pink title sticky
    # Phase 42 B1 (#13)：title_sticky 為空字串＝該 zone 不自動貼標題便條——
    # 視覺錨點改由組長進場的標題便條（kind=label）承擔（spec 28 §2.1 v2.0）。
    title_text = zone.visual.title_sticky if zone.visual else zone_id
    title_note_id: str | None = None
    if title_text:
        try:
            title_note_id = await canvas_ops.add_note(
                project_id=project_id,
                content=title_text,
                position={"x": final_bounds.x + 8, "y": final_bounds.y + 8},
                color="pink",
                author_id=author_id,
                author_name=author_name,
                author_type="ai",
            )
        except Exception as exc:
            logger.warning("draw_zone: title sticky creation failed: %s", exc)

    # 3. Best-effort broadcast
    try:
        await canvas_ops.broadcast_zone_drawn(  # type: ignore[attr-defined]
            project_id=project_id,
            zone_id=zone_id,
            bounds={
                "x": final_bounds.x,
                "y": final_bounds.y,
                "w": final_bounds.w,
                "h": final_bounds.h,
            },
            visual={
                "frame_shape": zone.visual.frame_shape if zone.visual else "rectangle",
                "border_color": zone.visual.border_color if zone.visual else "#94A3B8",
                "fill_pattern": zone.visual.fill_pattern if zone.visual else "dotted",
            },
        )
    except AttributeError:
        pass

    logger.info(
        "Agent %s draw_zone project=%s zone=%s bounds=(%s,%s,%s,%s)",
        author_id, project_id, zone_id,
        final_bounds.x, final_bounds.y, final_bounds.w, final_bounds.h,
    )

    return {
        "success": True,
        "zone_id": zone_id,
        "bounds": {
            "x": final_bounds.x, "y": final_bounds.y,
            "w": final_bounds.w, "h": final_bounds.h,
        },
        "title_note_id": title_note_id,
    }


# tool_draw_template 已整顆移除（Phase 42 補正 R3／P1-4）：目標 zone
# （empathy_×4／persona_card／journey_map）C1 已全刪，子呼叫必然全失敗但頂層
# 固定回 success=True 的殭屍工具；曾同時掛在 think/act 白名單並向 LLM 廣告。
# 現役開區工具＝tool_draw_zone（靜態 zone）＋ tool_open_section（動態 section）。
