"""Phase 25: multi-LLM-provider tier table + per-request logs + admin user seed

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-21
"""
from __future__ import annotations

import os
import uuid
from typing import Sequence, Union

import bcrypt
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMIN_EMAIL = "admin"
ADMIN_DISPLAY_NAME = "系統管理員"


def _initial_admin_password() -> str:
    pw = (os.environ.get("INITIAL_ADMIN_PASSWORD") or "").strip()
    if not pw:
        raise RuntimeError(
            "INITIAL_ADMIN_PASSWORD env var is required to seed the admin "
            "user. Set it in .env (see .env.example) before running migrations."
        )
    if len(pw) < 8:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 8 characters.")
    return pw


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def upgrade() -> None:
    bind = op.get_bind()

    # ── llm_providers ────────────────────────────────────────────────────
    op.create_table(
        "llm_providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("azure_api_version", sa.String(length=32), nullable=True),
        sa.Column("azure_deployment", sa.String(length=128), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column(
            "timeout_seconds", sa.Integer(), nullable=False, server_default="30"
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("tier BETWEEN 1 AND 5", name="ck_llm_provider_tier_range"),
        sa.CheckConstraint(
            "kind IN ('vllm', 'azure_openai')", name="ck_llm_provider_kind"
        ),
    )
    op.create_index(
        "idx_llm_provider_tier_enabled", "llm_providers", ["tier", "enabled"]
    )

    # ── llm_request_logs ─────────────────────────────────────────────────
    op.create_table(
        "llm_request_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llm_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tier_used", sa.Integer(), nullable=False),
        sa.Column("cascade_from_tier", sa.Integer(), nullable=True),
        sa.Column(
            "prompt_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "completion_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_class", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "caller", sa.String(length=64), nullable=False, server_default="unknown"
        ),
    )
    op.create_index(
        "idx_llm_log_created_at", "llm_request_logs", [sa.text("created_at DESC")]
    )
    op.create_index(
        "idx_llm_log_provider_created",
        "llm_request_logs",
        ["provider_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_llm_log_user_created",
        "llm_request_logs",
        ["user_id", sa.text("created_at DESC")],
    )

    # ── seed admin user ──────────────────────────────────────────────────
    existing = bind.execute(
        sa.text('SELECT id FROM "user" WHERE email = :e'),
        {"e": ADMIN_EMAIL},
    ).first()
    if existing is None:
        bind.execute(
            sa.text(
                """
                INSERT INTO "user" (id, email, password_hash, display_name, role, can_create_project)
                VALUES (:id, :email, :pw, :name, 'admin', false)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "email": ADMIN_EMAIL,
                "pw": _hash_password(_initial_admin_password()),
                "name": ADMIN_DISPLAY_NAME,
            },
        )

    # ── 不 seed 任何 LLM provider ─────────────────────────────────────────
    # Phase 25：provider 設定改為 DB 為唯一真理來源。Admin 第一次登入後請至
    # /admin/providers 自行新增 provider（vLLM / Azure OpenAI），不再有任何
    # endpoint / key 的預設值寫死於 migration 或 env 內。


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text('DELETE FROM "user" WHERE email = :e'), {"e": ADMIN_EMAIL})
    op.drop_index("idx_llm_log_user_created", table_name="llm_request_logs")
    op.drop_index("idx_llm_log_provider_created", table_name="llm_request_logs")
    op.drop_index("idx_llm_log_created_at", table_name="llm_request_logs")
    op.drop_table("llm_request_logs")
    op.drop_index("idx_llm_provider_tier_enabled", table_name="llm_providers")
    op.drop_table("llm_providers")
