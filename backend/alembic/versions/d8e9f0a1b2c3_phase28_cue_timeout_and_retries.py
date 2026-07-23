"""Phase 28: add project.cue_timeout_seconds + cue_max_retries

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-05-25

Phase 28 cue timeout 設計：人類被 cue 後的 timeout / retry 參數。
- cue_timeout_seconds：單次 timeout 秒數，預設 180（3 分鐘），允許 10-600。
- cue_max_retries：cue timeout 後 supervisor 最多 reminder 次數，預設 5，允許 0-10。
  ``0`` 表示「不 retry，第一次 timeout 就放棄」。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column(
            "cue_timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="180",
        ),
    )
    op.add_column(
        "project",
        sa.Column(
            "cue_max_retries",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )
    op.create_check_constraint(
        "ck_project_cue_timeout_seconds_range",
        "project",
        "cue_timeout_seconds BETWEEN 10 AND 600",
    )
    op.create_check_constraint(
        "ck_project_cue_max_retries_range",
        "project",
        "cue_max_retries BETWEEN 0 AND 10",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_project_cue_max_retries_range", "project", type_="check"
    )
    op.drop_constraint(
        "ck_project_cue_timeout_seconds_range", "project", type_="check"
    )
    op.drop_column("project", "cue_max_retries")
    op.drop_column("project", "cue_timeout_seconds")
