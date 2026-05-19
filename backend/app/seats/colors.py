"""Phase 22：席位識別色（sticky note 與聊天氣泡共用）

規則：
- 8 色與 tldraw / sidecar 預設色對齊
- 專案建立時，後端為每個席位 shuffle 出穩定色（之後不會變）
- 已鎖色的席位重複呼叫不會覆蓋
"""
from __future__ import annotations

import random
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.seat import Seat
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


async def assign_color_to_seat(
    session: AsyncSession, seat_id: UUID
) -> str | None:
    """為指定 seat 鎖定 sticky_color（若尚未鎖定）。回傳目前鎖定的色，或 None（找不到 seat）。"""
    seat = await session.get(Seat, seat_id)
    if seat is None:
        return None
    if seat.sticky_color:
        return seat.sticky_color

    used_result = await session.execute(
        select(Seat.sticky_color).where(
            Seat.project_id == seat.project_id,
            Seat.sticky_color.is_not(None),
        )
    )
    used = {row[0] for row in used_result.all() if row[0]}

    remaining = [c for c in STICKY_COLOR_POOL if c not in used]
    color = random.choice(remaining if remaining else list(STICKY_COLOR_POOL))

    seat.sticky_color = color
    await session.flush()
    return color


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


def seed_seat_colors(seats: list[Seat]) -> None:
    """專案建立時呼叫：為每個席位指派一個 sticky_color（shuffle 8 色）。"""
    pool = list(STICKY_COLOR_POOL)
    random.shuffle(pool)
    for idx, seat in enumerate(seats):
        if seat.sticky_color is None:
            seat.sticky_color = pool[idx % len(pool)]


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
