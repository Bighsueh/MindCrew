"""Phase 25 (extension): llm_request_payloads + admin_payload_access

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-05-21

Why a separate payloads table (vs JSONB columns on llm_request_logs):
- A single payload can be 50KB–2MB (system prompts + completion).
- Stats queries on llm_request_logs run every page load; we do not want them
  fighting with multi-MB TOAST'd JSONB / TEXT cells.
- 1:1 cold table keeps the hot path lean and isolates retention concerns.

admin_payload_access records every successful detail-modal open so the team
can audit which admin viewed which user's prompt — important because admins
can otherwise silently read student-authored content.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── llm_request_payloads (1:1 with llm_request_logs) ─────────────────
    op.create_table(
        "llm_request_payloads",
        sa.Column(
            "request_log_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_request_logs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("response_content", sa.Text(), nullable=True),
        sa.Column("response_finish_reason", sa.String(length=32), nullable=True),
        sa.Column(
            "messages_bytes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "idx_llm_payload_created_at",
        "llm_request_payloads",
        [sa.text("created_at DESC")],
    )

    # ── admin_payload_access (audit log for PII exposure) ────────────────
    op.create_table(
        "admin_payload_access",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "admin_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "request_log_id",
            sa.BigInteger(),
            sa.ForeignKey("llm_request_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_admin_payload_access_admin",
        "admin_payload_access",
        ["admin_user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_admin_payload_access_log",
        "admin_payload_access",
        ["request_log_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_admin_payload_access_log", table_name="admin_payload_access"
    )
    op.drop_index(
        "idx_admin_payload_access_admin", table_name="admin_payload_access"
    )
    op.drop_table("admin_payload_access")
    op.drop_index("idx_llm_payload_created_at", table_name="llm_request_payloads")
    op.drop_table("llm_request_payloads")
