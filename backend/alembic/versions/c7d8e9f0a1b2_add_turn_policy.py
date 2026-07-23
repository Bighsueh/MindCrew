"""Phase 28: add project.turn_policy (Turn-Taking Controller)

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-05-24

論文 RQ1/RQ2 自變項：三模式（cued / round_robin / open_floor）的可切換 turn-taking
policy。每個 project 一個值，預設 ``'cued'`` 以維持既有行為（Discover 階段 supervisor
主導點名）。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column(
            "turn_policy",
            sa.String(length=20),
            nullable=False,
            server_default="cued",
        ),
    )
    op.create_check_constraint(
        "ck_project_turn_policy",
        "project",
        "turn_policy IN ('cued', 'round_robin', 'open_floor')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_project_turn_policy", "project", type_="check")
    op.drop_column("project", "turn_policy")
