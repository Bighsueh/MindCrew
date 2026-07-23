"""Zone auto-seed — 進入 sub_phase 時自動畫出 / 註冊該 phase 宣告的 zones。

背景：zone 原本只在 Supervisor 主動呼叫 ``draw_zone`` 時才被註冊到 Redis 並畫出
dashed 框。沒有任何「進入 sub_phase 自動畫 zone」的 hook → 專案開局停在 1.1a 時
canvas 沒有任何 zone，agent 的 create_note 全部被 ``no_active_zone`` 硬拒絕。

本模組在 (a) sub_phase 推進、(b) agent 初次啟動 時，把 ``SUB_PHASES[sub_phase].zones``
宣告的 zone 以**既有** ``tool_draw_zone`` 畫出（register + 標題便條 + 廣播框事件）。
idempotent：已註冊的 zone 不重畫，避免重複標題便條。

RC1（spec 10 v2.0 §2.3/§9.6，2026-07-03）：zone bounds **由 section 模型推導**——
seed 當下以 ``compute_content_bottom`` 在白板最下方既有內容之下開帶（與動態
section 同一套硬計算），不再使用 default_bounds 的固定 y（那是未註冊時的
fallback 藍圖）。效果＝「phase 垂直堆疊、各自一條水平帶」，杜絕跨 phase 便條
物理堆疊。舊 phase 的註冊**刻意不清除**：帶模型下各安其帶、且下一帶的位置
計算需要它們的 bottom extent。
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.canvas.sections import (
    _EMPTY_BOARD_START_Y,
    SECTION_GAP,
    SECTION_START_X,
    compute_content_bottom,
)
from app.canvas.tools_zones import tool_draw_zone
from app.canvas.zone_registry import is_zone_registered
from app.canvas.zones import ZONES
from app.stages.sub_phases import get_sub_phase

logger = logging.getLogger(__name__)


async def compute_zone_band_bounds(
    project_id: UUID, zone_id: str
) -> dict[str, float] | None:
    """該 zone 的帶 bounds：沿用宣告的 w/h，y＝既有內容之下（x 固定左緣）。"""
    zone = ZONES.get(zone_id)
    if zone is None or zone.default_bounds is None:
        return None
    bottom = await compute_content_bottom(project_id)
    top = bottom + SECTION_GAP if bottom > 0.0 else _EMPTY_BOARD_START_Y
    return {
        "x": SECTION_START_X,
        "y": top,
        "w": zone.default_bounds.w,
        "h": zone.default_bounds.h,
    }


async def seed_zones_for_sub_phase(project_id: UUID, sub_phase_id: str) -> int:
    """把該 sub_phase 宣告的所有 zone 畫出（若尚未註冊）。回傳新畫的 zone 數。

    多 zone 的格（如 2.6）依宣告序依次往下疊帶：前一個 zone 註冊後，
    下一個的 ``compute_content_bottom`` 會看到它。
    """
    try:
        sub_phase = get_sub_phase(sub_phase_id)
    except KeyError:
        return 0

    drawn = 0
    for zone_id in sub_phase.zones:
        try:
            if await is_zone_registered(project_id, zone_id):
                continue
            band = await compute_zone_band_bounds(project_id, zone_id)
            result = await tool_draw_zone(
                project_id=project_id, zone_id=zone_id, bounds=band,
            )
            if result.get("success"):
                drawn += 1
        except Exception as exc:  # best-effort — 不可因畫 zone 失敗阻斷推進/啟動
            logger.warning(
                "seed_zones: draw zone %s failed project=%s: %s",
                zone_id, project_id, exc,
            )
    if drawn:
        logger.info(
            "seed_zones: drew %d zone(s) for sub_phase %s project=%s",
            drawn, sub_phase_id, project_id,
        )
    return drawn


async def seed_zones_for_current_sub_phase(project_id: UUID) -> int:
    """讀 project.current_sub_phase（Phase 38：預設暖場入口 0.0a）並 seed。用於 agent 初次啟動。"""
    from sqlalchemy import select

    from app.db.models.project import Project
    from app.db.session import async_session_factory

    sub_phase_id = "0.0a"
    try:
        async with async_session_factory() as session:
            row = await session.execute(
                select(Project.current_sub_phase).where(Project.id == project_id)
            )
            value = row.scalar_one_or_none()
            if value:
                sub_phase_id = value
    except Exception as exc:
        logger.debug("seed_zones: read current_sub_phase failed: %s", exc)

    return await seed_zones_for_sub_phase(project_id, sub_phase_id)
