"""Backfill: 為每個既有專案補一個空置的真人專屬席 ``human_creator``。

Revision ID: d5e6f7a8b9c0
Revises: e7f8a9b0c1d2
Create Date: 2026-06-08

Context
-------
座位模型改為「常駐 AI crew（crew_1..N）+ 1 個綁定 creator 的真人專屬席
``human_creator``（額外 +1）」。新建專案於 ``ProjectService.create_project`` 已會
種下這張席位；本 migration 為改版前建立、尚無此席的既有專案補上一張**空置**席。

空置真人席的表示（與 service / manager 一致）：
``occupant_type='human'`` + ``user_id IS NULL`` + ``state='vacant'``。
如此所有 ``occupant_type='ai'`` 的 agent 生成路徑都會天生跳過它。

Scope（保守）
------------
- 僅對「尚無 human_creator 席」的專案插入（以 ``WHERE NOT EXISTS`` 保證 idempotent，
  亦由 ``UNIQUE(project_id, seat_role)`` 兜底）。
- **不**搬遷「舊模型中已坐在 crew 席的真人」——團隊 dev DB 常重置、且本專案尚未上線，
  此偏離已記於 prompts/progress.md。
- ``sticky_color`` 留 NULL（依 Seat 模型，首次發訊息／貼便條時才鎖定）。

PostgreSQL 16：``gen_random_uuid()`` 為內建，無需額外 extension。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BACKFILL_SQL = sa.text(
    """
    INSERT INTO seat (
        id, project_id, seat_role, occupant_type,
        user_id, agent_id, state, persona, sticky_color, updated_at
    )
    SELECT
        gen_random_uuid(), p.id, 'human_creator', 'human',
        NULL, NULL, 'vacant', NULL, NULL, now()
    FROM project AS p
    WHERE NOT EXISTS (
        SELECT 1 FROM seat AS s
        WHERE s.project_id = p.id AND s.seat_role = 'human_creator'
    )
    """
)

_DOWNGRADE_SQL = sa.text(
    "DELETE FROM seat WHERE seat_role = 'human_creator'"
)


def upgrade() -> None:
    op.execute(_BACKFILL_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
