"""動態 section registry — Spec 10 v2.0 §2.3 / §5.9（Phase 42 C0 最小版）。

section 是「水平帶」版面單位：`open_section` 在白板**最下方既有內容之下**開一條
新的全寬帶。C0 最小版：靜態 ZONES 仍為過渡實作（spec 10 v2.0 註），動態 section
只服務 `open_section`（如 2.6 選定區）與 move-delta 事件的區名反推。

State 存 Redis key `sections:{project_id}` 為 hash：
  field: section_id
  value: JSON {"id":…, "title":…, "x":…, "y":…, "w":…, "h":…, "order":…}
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from uuid import UUID

from app.canvas.zone_registry import get_all_zones_for_project
from app.canvas.zones import Bounds
from app.config import settings

logger = logging.getLogger(__name__)

_REDIS_KEY_TMPL = "sections:{project_id}"

# 「往下開新帶」的硬計算常數（spec 10 §5.9：位置與帶高由硬邏輯配置）。
SECTION_START_X = 100.0
SECTION_BAND_WIDTH = 2400.0   # 全寬帶（與最大 zone 同量級）
SECTION_BAND_HEIGHT = 700.0
SECTION_GAP = 120.0           # 與上方既有內容的垂直間距
_EMPTY_BOARD_START_Y = 100.0


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def list_sections(project_id: UUID) -> list[dict[str, Any]]:
    """該專案所有動態 section（依 order 由上而下）。"""
    r = await _get_redis()
    try:
        raw_map = await r.hgetall(_REDIS_KEY_TMPL.format(project_id=project_id))
    finally:
        await r.aclose()

    sections: list[dict[str, Any]] = []
    for section_id, raw in raw_map.items():
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError(f"section payload 非 object：{type(data).__name__}")
            data["id"] = section_id
            sections.append(data)
        except Exception:
            # R1b-re：原本只接 JSONDecodeError/KeyError——合法 JSON 但非 object
            # （如 "5"）會以 TypeError 上炸，感知端整批吞成「無 section」、create
            # 端 get_section_bounds_map 直接讓工具爆掉。單筆壞資料＝跳過＋留痕，
            # 不放大成整表不可用。
            logger.warning(
                "Bad section entry project=%s section=%s", project_id, section_id,
                exc_info=True,
            )
    sections.sort(key=lambda s: s.get("order", 0))
    return sections


async def get_section(project_id: UUID, section_id: str) -> dict[str, Any] | None:
    r = await _get_redis()
    try:
        raw = await r.hget(_REDIS_KEY_TMPL.format(project_id=project_id), section_id)
    finally:
        await r.aclose()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        data["id"] = section_id
        return data
    except json.JSONDecodeError:
        return None


async def get_section_bounds_map(project_id: UUID) -> dict[str, Bounds]:
    """{section_id: Bounds}——layout engine `section:<id>` 落點解析用。"""
    return {
        s["id"]: Bounds(x=s["x"], y=s["y"], w=s["w"], h=s["h"])
        for s in await list_sections(project_id)
        if all(k in s for k in ("x", "y", "w", "h"))
    }


async def selection_members(project_id: UUID, notes: list[Any]) -> list[Any]:
    """選定區成員＝落在任一動態 section 帶內的便條（spec 25 §3.2 / spec 27 §14）。

    第一鑽石只有 2.6 會 ``open_section`` 開「選定區」，故任一動態 section ＝選定區
    （C0 設計：動態 section 只服務 open_section）。gate（artifact_gate）、結業
    （first_diamond_closing）、感知（tools_perception）三方共用此單一界定，避免「哪張
    被選中」在多處發散。section 不可達 → 空（best-effort）。
    """
    try:
        bounds_map = await get_section_bounds_map(project_id)
    except Exception:  # pragma: no cover - sections 不可達退空
        return []
    bounds_list = list(bounds_map.values())
    if not bounds_list:
        return []
    return [
        n for n in notes
        if any(
            b.contains(float(getattr(n, "x", 0.0)), float(getattr(n, "y", 0.0)))
            for b in bounds_list
        )
    ]


async def register_section(
    project_id: UUID,
    title: str,
    bounds: Bounds,
    order: int,
) -> dict[str, Any]:
    """寫入一條新 section，回傳完整 section dict（含生成的 section_id）。"""
    section_id = f"sec_{uuid.uuid4().hex[:8]}"
    payload = {
        "title": title,
        "x": bounds.x,
        "y": bounds.y,
        "w": bounds.w,
        "h": bounds.h,
        "order": order,
    }
    r = await _get_redis()
    try:
        await r.hset(
            _REDIS_KEY_TMPL.format(project_id=project_id),
            section_id,
            json.dumps(payload),
        )
    finally:
        await r.aclose()
    logger.info(
        "Section registered project=%s section=%s title=%s y=%s",
        project_id, section_id, title, bounds.y,
    )
    return {"id": section_id, **payload}


async def clear_project_sections(project_id: UUID) -> None:
    r = await _get_redis()
    try:
        await r.delete(_REDIS_KEY_TMPL.format(project_id=project_id))
    finally:
        await r.aclose()


def resolve_section_by_position(
    sections: list[dict[str, Any]], x: float, y: float
) -> dict[str, Any] | None:
    """(x, y) 落在哪條動態 section（move-delta 區名反推用）。"""
    for s in sections:
        try:
            b = Bounds(x=s["x"], y=s["y"], w=s["w"], h=s["h"])
        except KeyError:
            continue
        if b.contains(x, y):
            return s
    return None


async def compute_content_bottom(project_id: UUID) -> float:
    """全板內容下緣＝max(已註冊 zone、動態 section、所有便條的 bottom extent)。

    「往下開新帶」的共用基準（spec 10 §2.3 單一真理來源）：動態 section
    （``compute_open_section_bounds``）與靜態 zone 帶（``zone_seed``）都由此推導。
    空白板回 0.0。
    """
    bottom = 0.0

    zone_bounds = await get_all_zones_for_project(project_id)
    for b in zone_bounds.values():
        bottom = max(bottom, b.y + b.h)

    for s in await list_sections(project_id):
        try:
            bottom = max(bottom, float(s["y"]) + float(s["h"]))
        except (KeyError, TypeError, ValueError):
            continue

    from app.bridge.canvas_ops import canvas_ops

    for shape in await canvas_ops.get_canvas_state_full(project_id):
        try:
            bottom = max(
                bottom, float(shape["y"]) + float(shape.get("height", 150.0))
            )
        except (KeyError, TypeError, ValueError):
            continue

    return bottom


async def compute_open_section_bounds(project_id: UUID) -> tuple[Bounds, int]:
    """「往下開新帶」bounds 硬計算（spec 10 §5.9）。

    新帶 top = ``compute_content_bottom`` + GAP；全空白板從 _EMPTY_BOARD_START_Y 起。
    全寬帶、固定帶高。回 (bounds, order)。
    """
    bottom = await compute_content_bottom(project_id)
    top = bottom + SECTION_GAP if bottom > 0.0 else _EMPTY_BOARD_START_Y
    bounds = Bounds(
        x=SECTION_START_X, y=top, w=SECTION_BAND_WIDTH, h=SECTION_BAND_HEIGHT
    )
    sections = await list_sections(project_id)
    order = (max((s.get("order", 0) for s in sections), default=0)) + 1
    return bounds, order
