"""add timer config and state columns

Spec 15: project 新增 timer_config / timer_state JSONB。

Revision ID: 3b4c5d6e7f8a
Revises: 2a3b4c5d6e7f
Create Date: 2026-05-11 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '3b4c5d6e7f8a'
down_revision: Union[str, Sequence[str], None] = '2a3b4c5d6e7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'project',
        sa.Column('timer_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'project',
        sa.Column('timer_state', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('project', 'timer_state')
    op.drop_column('project', 'timer_config')
