"""Phase 34: add project.first_diamond_output JSONB

Revision ID: a2b3c4d5e6f7
Revises: f1b2c3d4e5f6
Create Date: 2026-05-26

Phase 34 第一鑽石終局儀式：
- ``first_diamond_output``：JSONB 結構，紀錄第一鑽石的最終成果，
  包含 personas / chosen_problem_statement / chosen_hmw / completed_at。
- 由 closing ritual 在 stage advance 到 'completed' 後寫入。
- nullable，未完成第一鑽石的 project 為 NULL。

依據 spec/26-first-diamond-closing.md。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column(
            "first_diamond_output",
            sa.dialects.postgresql.JSONB(),  # type: ignore[attr-defined]
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("project", "first_diamond_output")
