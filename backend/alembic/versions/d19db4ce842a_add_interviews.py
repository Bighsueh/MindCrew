"""Add standalone stakeholder interviews.

Revision ID: d19db4ce842a
Revises: a1b2c3d4e5a6
"""

import sqlalchemy as sa
from alembic import op

revision = "d19db4ce842a"
down_revision = "a1b2c3d4e5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stakeholder_id", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_interview_sessions_owner_started", "interview_sessions", ["owner_id", "started_at"])
    op.create_table(
        "interview_exchanges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("provider", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("attempt_token", sa.Uuid()),
        sa.Column("waiting_until", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("session_id", "sequence", name="uq_interview_exchange_sequence"),
        sa.UniqueConstraint("session_id", "request_id", name="uq_interview_exchange_request"),
    )


def downgrade() -> None:
    op.drop_table("interview_exchanges")
    op.drop_index("ix_interview_sessions_owner_started", table_name="interview_sessions")
    op.drop_table("interview_sessions")
