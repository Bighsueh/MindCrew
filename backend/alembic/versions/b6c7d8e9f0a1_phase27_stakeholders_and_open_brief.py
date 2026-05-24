"""phase27_stakeholders_and_open_brief

Phase 27：開放任務簡報 + 利害關係人勾選
- project.stakeholders: JSONB NOT NULL DEFAULT '[]'
    建立時使用者勾選的利害關係人清單
    Shape: [{ id, name, role, relevance, selected: true }]
- project.task_brief_kind: VARCHAR(16) NOT NULL DEFAULT 'legacy'
    'open' 表示 Phase 27 後的 open brief 流程
    'legacy' 為 Phase 27 前資料（保留以利 Lobby StakeholderPanel graceful skip）

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-05-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "project",
        sa.Column(
            "stakeholders",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "project",
        sa.Column(
            "task_brief_kind",
            sa.String(length=16),
            nullable=False,
            server_default="legacy",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("project", "task_brief_kind")
    op.drop_column("project", "stakeholders")
