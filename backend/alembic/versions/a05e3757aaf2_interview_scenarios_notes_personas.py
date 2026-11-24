"""Add interview scenario snapshots, notes and student personas."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "a05e3757aaf2"
down_revision = "d19db4ce842a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interview_sessions", sa.Column("scenario_snapshot", JSONB()))
    op.add_column("interview_sessions", sa.Column("note_body", sa.Text()))
    op.add_column("interview_sessions", sa.Column("note_updated_at", sa.DateTime(timezone=True)))
    op.create_table(
        "interview_personas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("fields", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interview_personas_owner_updated", "interview_personas", ["owner_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_interview_personas_owner_updated", table_name="interview_personas")
    op.drop_table("interview_personas")
    op.drop_column("interview_sessions", "note_updated_at")
    op.drop_column("interview_sessions", "note_body")
    op.drop_column("interview_sessions", "scenario_snapshot")
