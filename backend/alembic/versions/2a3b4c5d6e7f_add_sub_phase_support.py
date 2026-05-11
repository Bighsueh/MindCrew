"""add_sub_phase_support

Spec 13 Sticky-Only Strategy 引入 sub-phase 概念。
project 新增 current_sub_phase；agent_decision_trace 新增 sub_phase + zone_id 欄位。

Revision ID: 2a3b4c5d6e7f
Revises: 1fdee7446bf9
Create Date: 2026-05-11 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a3b4c5d6e7f'
down_revision: Union[str, Sequence[str], None] = '1fdee7446bf9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Project: current_sub_phase 允許 nullable（過渡期），預設 None → 沿用 micro_phase
    op.add_column(
        'project',
        sa.Column('current_sub_phase', sa.String(length=8), nullable=True),
    )

    # Agent decision trace: 紀錄 sub-phase 與 zone
    op.add_column(
        'agent_decision_trace',
        sa.Column('sub_phase', sa.String(length=8), nullable=True),
    )
    op.add_column(
        'agent_decision_trace',
        sa.Column('zone_id', sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('agent_decision_trace', 'zone_id')
    op.drop_column('agent_decision_trace', 'sub_phase')
    op.drop_column('project', 'current_sub_phase')
