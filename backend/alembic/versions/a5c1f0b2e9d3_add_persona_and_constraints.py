"""add_persona_and_constraints

Phase 19: 動態 AI 人設系統
- project.constraints: TEXT (專案限制，激發創意與聚焦)
- seat.persona: JSONB (per-project 動態人設快照)

Revision ID: a5c1f0b2e9d3
Revises: 1fdee7446bf9
Create Date: 2026-05-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a5c1f0b2e9d3'
down_revision: Union[str, Sequence[str], None] = '1fdee7446bf9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'project',
        sa.Column('constraints', sa.Text(), nullable=True),
    )
    op.add_column(
        'seat',
        sa.Column(
            'persona',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('seat', 'persona')
    op.drop_column('project', 'constraints')
