"""Phase 26 / S2 — encrypt existing llm_providers.api_key in place.

Reads every row with a non-empty plaintext api_key and rewrites it as a
``fernet:<token>`` ciphertext using ``LLM_PROVIDER_KEY_MASTER`` (or the
dev-fallback derived key). Idempotent — values already prefixed with
``fernet:`` are skipped.

Downgrade attempts to decrypt back to plaintext. If the master key is wrong
the migration aborts loudly rather than silently leaving unreadable data.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.security.secrets import (
    decrypt_secret,
    encrypt_secret,
    is_ciphertext,
)

# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, api_key FROM llm_providers")
    ).fetchall()
    for row_id, api_key in rows:
        if not api_key or is_ciphertext(api_key):
            continue
        new_value = encrypt_secret(api_key)
        bind.execute(
            sa.text("UPDATE llm_providers SET api_key = :v WHERE id = :id"),
            {"v": new_value, "id": row_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, api_key FROM llm_providers")
    ).fetchall()
    for row_id, api_key in rows:
        if not api_key or not is_ciphertext(api_key):
            continue
        plain = decrypt_secret(api_key)
        bind.execute(
            sa.text("UPDATE llm_providers SET api_key = :v WHERE id = :id"),
            {"v": plain, "id": row_id},
        )
