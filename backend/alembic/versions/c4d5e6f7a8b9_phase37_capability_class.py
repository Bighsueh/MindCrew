"""Phase 37: capability_class quality-pool routing axis.

Adds the orthogonal-to-tier quality pool:
  - ``llm_providers.capability_class``      ('quality' | 'standard', default 'standard')
  - ``llm_request_logs.capability_class_used`` (nullable; observability)

Existing providers default to 'standard'; gemma models are promoted to
'quality' so the seed inventory routes correctly out of the box. See
``specs/06 §1.10`` / ``specs/03 §4.1.2`` (v4.17) and
``_discussion/docs/llm-tiering-and-agent-think-optimization.md``.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # llm_providers.capability_class — NOT NULL with default backfills existing rows.
    op.add_column(
        "llm_providers",
        sa.Column(
            "capability_class",
            sa.String(length=16),
            nullable=False,
            server_default="standard",
        ),
    )
    op.create_check_constraint(
        "ck_llm_provider_capability_class",
        "llm_providers",
        "capability_class IN ('quality', 'standard')",
    )
    op.create_index(
        "idx_llm_provider_class_enabled",
        "llm_providers",
        ["capability_class", "enabled"],
    )
    # Seed inventory: gemma is the strong-but-slow model → quality pool.
    op.execute(
        sa.text(
            "UPDATE llm_providers SET capability_class = 'quality' "
            "WHERE model ILIKE '%gemma%'"
        )
    )

    # llm_request_logs.capability_class_used — which pool actually served the call.
    op.add_column(
        "llm_request_logs",
        sa.Column("capability_class_used", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_request_logs", "capability_class_used")
    op.drop_index("idx_llm_provider_class_enabled", table_name="llm_providers")
    op.drop_constraint(
        "ck_llm_provider_capability_class", "llm_providers", type_="check"
    )
    op.drop_column("llm_providers", "capability_class")
