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

logger = logging.getLogger(__name__)


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
    title_text = zone.visual.title_sticky if zone.visual else zone_id
    title_note_id: str | None = None
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


async def tool_draw_template(
    project_id: UUID,
    template: str,
    origin: tuple[float, float] | None = None,
    author_id: str = "system",
    author_name: str = "System",
) -> dict[str, Any]:
    """一次畫完整套模板（Empathy Map / Persona / Journey Map）。

    template ∈ {"empathy_map", "persona", "journey_map"}
    """
    if template == "empathy_map":
        zone_ids = ("empathy_says", "empathy_thinks", "empathy_does", "empathy_feels")
    elif template == "persona":
        zone_ids = ("persona_card",)
    elif template == "journey_map":
        zone_ids = ("journey_map",)
    else:
        return {"success": False, "error": f"Unknown template: {template}"}

    drawn: list[dict[str, Any]] = []
    for zone_id in zone_ids:
        result = await tool_draw_zone(
            project_id=project_id,
            zone_id=zone_id,
            bounds=None,  # use default
            author_id=author_id,
            author_name=author_name,
        )
        drawn.append(result)

    return {"success": True, "template": template, "zones": drawn}
