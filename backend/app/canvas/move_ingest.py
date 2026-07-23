"""Move-delta 事件單一消費點（Spec 10 v2.0 §4.7，Phase 42 C0）。

從 sidecar ring buffer 拉事件（Redis cursor 防重複，C0 裁定 1：backend 拉、不做
webhook；buffer 重啟即失），語意化後寫入 Redis `canvas_moves:{project_id}` 供
context_buffer 注入 LLM context；真人 move 同步餵 round_lock（move 型關卡解鎖，
spec 20 §11.4——A2 留的洞）。呼叫點掛 progression watcher 的 per-project tick
（C0 裁定 6）。

區名反推：動態 section（containment）優先，其次靜態 zone（過渡實作）；
真人顯示名由席位表解析（單真人席前提）。
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.canvas.sections import list_sections, resolve_section_by_position
from app.canvas.zone_registry import get_all_zones_for_project
from app.canvas.zones import resolve_zone_by_position
from app.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

_CURSOR_KEY_TMPL = "move_events:cursor:{project_id}"
_MOVES_KEY_TMPL = "canvas_moves:{project_id}"
_MOVES_LIMIT = 30
_CURSOR_TTL = 86400


async def _get_redis() -> Any:
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _project_facts(project_id: UUID) -> tuple[str | None, str | None]:
    """(current_sub_phase, 真人顯示名)。真人席空置 → 顯示名 None。"""
    from app.db.models.project import Project
    from app.db.models.seat import Seat
    from app.db.models.user import User

    async with async_session_factory() as session:
        sub_phase = (
            await session.execute(
                select(Project.current_sub_phase).where(Project.id == project_id)
            )
        ).scalar_one_or_none()
        human_name = (
            await session.execute(
                select(User.display_name)
                .join(Seat, Seat.user_id == User.id)
                .where(
                    Seat.project_id == project_id,
                    Seat.occupant_type == "human",
                )
            )
        ).scalars().first()
    return sub_phase, human_name


def _area_name(
    x: float,
    y: float,
    sub_phase: str | None,
    zone_bounds: dict,
    sections: list[dict[str, Any]],
) -> str:
    """座標 → 學生看得懂的區名（動態 section 優先、靜態 zone 次之）。"""
    section = resolve_section_by_position(sections, x, y)
    if section is not None:
        return str(section.get("title") or "新開的區")
    if sub_phase:
        zone = resolve_zone_by_position(
            x, y, sub_phase, project_zone_bounds=zone_bounds or None
        )
        if zone is not None:
            # Phase 42 C1（#13）：框標題留空後，in-scene 短名由 ZONE_NAMES_ZH 供應。
            from app.canvas.zones import ZONE_NAMES_ZH

            named = ZONE_NAMES_ZH.get(zone.id)
            if named:
                return named
            if zone.visual and zone.visual.title_sticky:
                return zone.visual.title_sticky
            if zone.description:
                return zone.description[:20]
    return "未分區"


def _enrich(
    event: dict[str, Any],
    sub_phase: str | None,
    zone_bounds: dict,
    sections: list[dict[str, Any]],
    human_name: str | None,
) -> dict[str, Any]:
    before = event.get("before") or {}
    after = event.get("after") or {}
    is_human = bool(event.get("is_human"))
    moved_by = str(event.get("moved_by") or "system")
    if is_human:
        display = human_name or "使用者"
    else:
        # author tag "Name(ai)" → "Name"；system / 系統讓位原樣
        display = moved_by.removesuffix("(ai)")
    return {
        "seq": event.get("seq"),
        "note_id": event.get("note_id"),
        "content": event.get("content") or "",
        "moved_by": display,
        "is_human": is_human,
        "from_area": _area_name(
            float(before.get("x", 0)), float(before.get("y", 0)),
            sub_phase, zone_bounds, sections,
        ),
        "to_area": _area_name(
            float(after.get("x", 0)), float(after.get("y", 0)),
            sub_phase, zone_bounds, sections,
        ),
        "from_group": before.get("group_id"),
        "to_group": after.get("group_id"),
        "neighbors": [
            {"content": n.get("content") or "", "group_id": n.get("group_id")}
            for n in (event.get("neighbors_after") or [])[:3]
        ],
        "moved_at": event.get("moved_at"),
    }


async def ingest_moves(project_id: UUID) -> int:
    """拉新事件 → 語意化入 Redis ＋ 真人 move 解鎖。回傳本次消化的事件數。

    Cursor 防重複：以 sidecar 遞增 seq 為界，只消化 seq > cursor 的事件；
    失敗時 cursor 不前進（下個 tick 重拉，事件不漏不重）。
    """
    from app.bridge.canvas_ops import canvas_ops

    r = await _get_redis()
    cursor_key = _CURSOR_KEY_TMPL.format(project_id=project_id)
    moves_key = _MOVES_KEY_TMPL.format(project_id=project_id)
    try:
        raw_cursor = await r.get(cursor_key)
        cursor = int(raw_cursor) if raw_cursor else 0

        data = await canvas_ops.get_move_events(project_id, since=cursor)
        events = data.get("events") or []
        latest_seq = int(data.get("latest_seq") or cursor)
        if not events:
            # ring 已 trim 但無新事件 → cursor 跟上，避免卡死重拉
            if latest_seq > cursor:
                await r.set(cursor_key, str(latest_seq), ex=_CURSOR_TTL)
            return 0

        sub_phase, human_name = await _project_facts(project_id)
        zone_bounds = await get_all_zones_for_project(project_id)
        sections = await list_sections(project_id)

        human_moved = False
        pipe = r.pipeline()
        for event in events:
            enriched = _enrich(event, sub_phase, zone_bounds, sections, human_name)
            pipe.rpush(moves_key, json.dumps(enriched, ensure_ascii=False))
            if enriched["is_human"]:
                human_moved = True
        pipe.ltrim(moves_key, -_MOVES_LIMIT, -1)
        pipe.set(cursor_key, str(max(latest_seq, cursor)), ex=_CURSOR_TTL)
        await pipe.execute()

        if human_moved and sub_phase:
            from app.agents.round_lock import register_human_input

            await register_human_input(project_id, sub_phase, "move")

        return len(events)
    except Exception:
        logger.debug("ingest_moves failed project=%s", project_id, exc_info=True)
        return 0
    finally:
        await r.aclose()
