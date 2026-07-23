"""Phase 30: add project.tour_acknowledged_by JSONB

Revision ID: f1b2c3d4e5f6
Revises: e0f1a2b3c4d5
Create Date: 2026-05-26

Phase 30 強化第一鑽石的 Phase 0（暖場 + DEMO 導覽 + 任務理解）：
- ``tour_acknowledged_by``：JSONB 字典 ``{user_id: ISO8601 timestamp}``，
  紀錄每位 user 在哪一刻完成 DEMO 導覽。前端進入 workspace 時若該 user
  不在 map 內，顯示 0.1 sub_phase 的 DEMO 導覽；user 確認後寫入此欄位。

依據 spec/04-06-micro-phase-state.md §4.1 / spec/22-first-diamond-9-steps.md。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column(
            "tour_acknowledged_by",
            sa.dialects.postgresql.JSONB(),  # type: ignore[attr-defined]
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("project", "tour_acknowledged_by")
