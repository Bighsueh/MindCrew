"""Phase 25 (extension): split user_id into owning/triggered + add project_id

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-05-21

Schema change rationale (see plan §設計決策):
- Every LLM call must have an owning user (NOT NULL, billing/attribution).
- The user who *triggered* the call is a separate concept — many agent calls
  fire on internal ticks with no trigger; the owner is then the project's
  linked teacher (or, for non-project calls, the caller's authenticated user).
- project_id lets admin filter logs by context; nullable because some calls
  (e.g. persona generation prior to project creation) have no project yet.

Backfill: existing NULL user_ids are assigned to the seeded admin user as a
final-resort owner. There is no way to infer the original project from a row
that never had project_id, so we accept this and document it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. add project_id (nullable) ──────────────────────────────────────
    op.add_column(
        "llm_request_logs",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ── 2. add triggered_by_user_id (nullable) ────────────────────────────
    op.add_column(
        "llm_request_logs",
        sa.Column(
            "triggered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ── 3. rename user_id → owning_user_id ────────────────────────────────
    op.alter_column(
        "llm_request_logs",
        "user_id",
        new_column_name="owning_user_id",
    )

    # The existing index `idx_llm_log_user_created` referenced user_id; Postgres
    # tracks the column by id so the index now silently covers owning_user_id.
    # Rename it to match for clarity.
    op.execute(
        "ALTER INDEX idx_llm_log_user_created RENAME TO idx_llm_log_owning_user_created"
    )

    # ── 4. backfill NULL owning_user_id → seeded admin user ───────────────
    admin_row = bind.execute(
        sa.text("SELECT id FROM \"user\" WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1")
    ).first()
    if admin_row is not None:
        bind.execute(
            sa.text(
                "UPDATE llm_request_logs SET owning_user_id = :uid "
                "WHERE owning_user_id IS NULL"
            ),
            {"uid": admin_row[0]},
        )
    else:
        # No admin seeded — should not happen because d2e3f4a5b6c7 seeds one.
        # Delete the orphan rows instead of carrying a NULL through the NOT NULL.
        bind.execute(sa.text("DELETE FROM llm_request_logs WHERE owning_user_id IS NULL"))

    # ── 5. ALTER owning_user_id NOT NULL ──────────────────────────────────
    op.alter_column(
        "llm_request_logs",
        "owning_user_id",
        nullable=False,
        existing_type=postgresql.UUID(as_uuid=True),
    )

    # ── 6. index for project filter ───────────────────────────────────────
    op.create_index(
        "idx_llm_log_project_created",
        "llm_request_logs",
        ["project_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_llm_log_project_created", table_name="llm_request_logs")
    op.alter_column(
        "llm_request_logs",
        "owning_user_id",
        nullable=True,
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.execute(
        "ALTER INDEX idx_llm_log_owning_user_created RENAME TO idx_llm_log_user_created"
    )
    op.alter_column(
        "llm_request_logs",
        "owning_user_id",
        new_column_name="user_id",
    )
    op.drop_column("llm_request_logs", "triggered_by_user_id")
    op.drop_column("llm_request_logs", "project_id")
