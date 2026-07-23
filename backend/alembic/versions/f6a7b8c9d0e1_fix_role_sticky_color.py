"""Backfill：把既有席位的 ``sticky_color`` 對齊「角色固定專屬色」。

Revision ID: f6a7b8c9d0e1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-09

Context
-------
席位識別色改為「每個角色一個全站固定專屬色」（取代先前每專案 shuffle 的隨機色），
使便條色 = 聊天色 = 角色身分。新建專案於 ``seed_seat_colors`` 已套用固定映射；
本 migration 把改版前已建立、帶隨機色的既有專案席位一併對齊。

對照（與 ``app/seats/colors.py::ROLE_COLOR_MAP`` 一致）：
``supervisor→red``（陶土）、``human_creator→blue``、``crew_1→yellow``、
``crew_2→green``、``crew_3→violet``、``crew_4→orange``。

Scope
-----
- 覆寫上述角色的 ``sticky_color``（含已有隨機色者），其餘 seat_role 不動。
- ``human_creator`` 由原本可能 NULL 改為 ``blue``（與 service 新行為一致）。

downgrade 無法還原先前的隨機色，故為 no-op（此偏離已記於 prompts/progress.md）。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPGRADE_SQL = sa.text(
    """
    UPDATE seat
    SET sticky_color = CASE seat_role
        WHEN 'supervisor'    THEN 'red'
        WHEN 'human_creator' THEN 'blue'
        WHEN 'crew_1'        THEN 'yellow'
        WHEN 'crew_2'        THEN 'green'
        WHEN 'crew_3'        THEN 'violet'
        WHEN 'crew_4'        THEN 'orange'
        ELSE sticky_color
    END
    WHERE seat_role IN (
        'supervisor', 'human_creator', 'crew_1', 'crew_2', 'crew_3', 'crew_4'
    )
    """
)


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    # 先前的隨機色無法還原；維持固定色（no-op）。
    pass
