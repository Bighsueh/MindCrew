"""Per-project zone registry — Spec 13 §2.

Supervisor 在 sub-phase 進入時呼叫 draw_zone，將 zone 的實際 bounds 寫入此 registry。
後端 create_note 時用 resolve_zone_by_position(x, y, sub_phase, project_bounds) 判定。

State 存在 Redis key `zones:{project_id}` 為 hash：
  field: zone_id
  value: JSON {"x":..., "y":..., "w":..., "h":...}
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from app.canvas.zones import Bounds, ZONES
from app.config import settings

logger = logging.getLogger(__name__)

_REDIS_KEY_TMPL = "zones:{project_id}"


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def register_zone(
    project_id: UUID,
    zone_id: str,
    bounds: Bounds,
) -> None:
    """Persist a zone's actual bounds for a project."""
    if zone_id not in ZONES:
        raise KeyError(f"Unknown zone id: {zone_id!r}")

    r = await _get_redis()
    try:
        payload = json.dumps({
            "x": bounds.x,
            "y": bounds.y,
            "w": bounds.w,
            "h": bounds.h,
        })
        await r.hset(
            _REDIS_KEY_TMPL.format(project_id=project_id),
            zone_id,
            payload,
        )
    finally:
        await r.aclose()
    logger.info(
        "Zone registered project=%s zone=%s bounds=(%s,%s,%s,%s)",
        project_id, zone_id, bounds.x, bounds.y, bounds.w, bounds.h,
    )


async def unregister_zone(project_id: UUID, zone_id: str) -> None:
    r = await _get_redis()
    try:
        await r.hdel(_REDIS_KEY_TMPL.format(project_id=project_id), zone_id)
    finally:
        await r.aclose()


async def get_zone_bounds(
    project_id: UUID,
    zone_id: str,
) -> Bounds | None:
    """Return registered bounds for a project's zone; None if not registered."""
    r = await _get_redis()
    try:
        raw = await r.hget(_REDIS_KEY_TMPL.format(project_id=project_id), zone_id)
    finally:
        await r.aclose()

    if not raw:
        return None
    data = json.loads(raw)
    return Bounds(x=data["x"], y=data["y"], w=data["w"], h=data["h"])


async def get_all_zones_for_project(
    project_id: UUID,
) -> dict[str, Bounds]:
    """Return all registered zones {zone_id -> bounds} for a project."""
    r = await _get_redis()
    try:
        raw_map = await r.hgetall(_REDIS_KEY_TMPL.format(project_id=project_id))
    finally:
        await r.aclose()

    result: dict[str, Bounds] = {}
    for zone_id, raw in raw_map.items():
        try:
            data = json.loads(raw)
            result[zone_id] = Bounds(
                x=data["x"], y=data["y"], w=data["w"], h=data["h"],
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Bad zone registry entry project=%s zone=%s", project_id, zone_id)
    return result


async def clear_project_zones(project_id: UUID) -> None:
    """Remove all zone registrations for a project."""
    r = await _get_redis()
    try:
        await r.delete(_REDIS_KEY_TMPL.format(project_id=project_id))
    finally:
        await r.aclose()


async def is_zone_registered(project_id: UUID, zone_id: str) -> bool:
    bounds = await get_zone_bounds(project_id, zone_id)
    return bounds is not None
