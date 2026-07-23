"""Backfill: re-attribute historical autonomous agent ticks from the admin
fallback to the project creator.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-05

Context
-------
``SeatManager._resolve_owning_user`` previously read a non-existent
``project.owner_id`` and fell through to the seeded **admin** user whenever a
project had no linked teacher. As a result, every autonomous agent tick
(``triggered_by_user_id IS NULL``) on a teacher-less project had its tokens
attributed to the admin account, polluting the per-user stats.

The code fix (use ``project.creator_id``) corrects this going forward. This
data migration repairs the history so the admin Stats page reflects reality.

Scope (deliberately conservative)
---------------------------------
Only rows that are clearly the bug's victims are touched:
  - ``triggered_by_user_id IS NULL``  (autonomous tick, no human action)
  - ``owning_user_id`` is currently an **admin** user
  - ``owning_user_id <> project.creator_id``  (skip no-ops; an admin who truly
    created the project keeps ownership)

Rows already attributed to a (non-admin) linked teacher are intentionally left
as-is to avoid rewriting legitimate class-cost attribution; only the admin
fallback is corrected.

This is a one-way data fix; ``downgrade`` is a no-op (the prior admin id is not
recoverable).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BACKFILL_SQL = sa.text(
    """
    UPDATE llm_request_logs AS l
    SET owning_user_id = p.creator_id
    FROM project AS p
    WHERE l.project_id = p.id
      AND l.triggered_by_user_id IS NULL
      AND l.owning_user_id <> p.creator_id
      AND l.owning_user_id IN (
          SELECT id FROM "user" WHERE role = 'admin'
      )
    """
)


def upgrade() -> None:
    op.execute(_BACKFILL_SQL)


def downgrade() -> None:
    # One-way data backfill — the original (incorrect) admin attribution is not
    # stored anywhere, so there is nothing to restore.
    pass
