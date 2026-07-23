"""席位識別色（sticky note 與聊天氣泡共用）。

規則（使用者拍板）：
- 每個角色（seat_role）有一個「全站固定」的專屬色，跨專案一致。
- 同一份色同時用於畫布便條與聊天氣泡，使「便條色 = 聊天色」。
- 只取畫布（tldraw COLOR_MAP）與聊天（sticky.ts SCHEMES）都原生支援、且渲染相異的 6 色。
- light-blue / light-green 仍保留在 8 色池中（fallback 用），但不指派給角色。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.seat import (
    SEAT_ROLE_HUMAN_CREATOR,
    SEAT_ROLE_SUPERVISOR,
    Seat,
)
from app.db.session import async_session_factory


STICKY_COLOR_POOL: tuple[str, ...] = (
    "yellow",
    "orange",
    "green",
    "blue",
    "violet",
    "red",
    "light-blue",
    "light-green",
)

# 角色 → 專屬色（全站固定）。supervisor = red（tldraw red 即「陶土」，保留組長識別）。
ROLE_COLOR_MAP: dict[str, str] = {
    SEAT_ROLE_SUPERVISOR: "red",
    SEAT_ROLE_HUMAN_CREATOR: "blue",
    "crew_1": "yellow",
    "crew_2": "green",
    "crew_3": "violet",
    "crew_4": "orange",
}

# 未知角色（理論上不會出現）的決定性 fallback。
_FALLBACK_COLOR: str = "light-blue"


def color_for_role(seat_role: str) -> str:
    """角色 → 固定專屬色（決定性，無隨機）。"""
    return ROLE_COLOR_MAP.get(seat_role, _FALLBACK_COLOR)


def seed_seat_colors(seats: list[Seat]) -> None:
    """專案建立時呼叫：依角色為每個席位指派固定專屬色（未鎖色者才寫入）。"""
    for seat in seats:
        if seat.sticky_color is None:
            seat.sticky_color = color_for_role(seat.seat_role)


async def assign_color_to_seat(
    session: AsyncSession, seat_id: UUID
) -> str | None:
    """為指定 seat 鎖定 sticky_color（若尚未鎖定）。回傳鎖定的色，或 None（找不到 seat）。"""
    seat = await session.get(Seat, seat_id)
    if seat is None:
        return None
    if seat.sticky_color:
        return seat.sticky_color

    seat.sticky_color = color_for_role(seat.seat_role)
    await session.flush()
    return seat.sticky_color


async def get_seat_color_by_role(
    session: AsyncSession, project_id: UUID, seat_role: str
) -> str | None:
    """讀 seat 目前的 sticky_color（不會 lazy-assign）。"""
    result = await session.execute(
        select(Seat.sticky_color).where(
            Seat.project_id == project_id,
            Seat.seat_role == seat_role,
        )
    )
    row = result.first()
    return row[0] if row else None


async def lookup_color_for_author(
    project_id: UUID, author_id: str | None, author_type: str
) -> str | None:
    """以 author_id 找到對應 seat 的 sticky_color。

    - system author 或空值 → None（不 override，保留呼叫端指定色）
    - human → 用 user_id 對應
    - ai → 嘗試用 agent_id 對應（AI agent 的 author_id 即為 agent_id）
    """
    if not author_id or author_id == "system":
        return None
    async with async_session_factory() as session:
        try:
            if author_type == "human":
                user_uuid = UUID(author_id)
                stmt = select(Seat.sticky_color).where(
                    Seat.project_id == project_id,
                    Seat.user_id == user_uuid,
                )
            else:
                stmt = select(Seat.sticky_color).where(
                    Seat.project_id == project_id,
                    Seat.agent_id == author_id,
                )
            result = await session.execute(stmt)
            row = result.first()
            return row[0] if row else None
        except (ValueError, Exception):
            return None
