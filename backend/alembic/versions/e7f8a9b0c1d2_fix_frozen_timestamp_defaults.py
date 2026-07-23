"""Fix frozen created_at/updated_at server defaults.

The initial schema (and several later migrations) declared timestamp columns
with ``server_default='now()'`` as a *plain Python string*. SQLAlchemy emits a
bare string server-default as a quoted SQL literal — ``DEFAULT 'now()'`` —
which Postgres evaluates **once** at DDL time and freezes into a constant
timestamp. The net effect: every row inserted afterwards inherits the same
frozen creation time (observed in prod as ``2026-05-11 08:06:34.149172+00``),
so the UI showed every project/message as created at the same instant.

This migration replaces the frozen literal default with a live ``now()``
function call on every affected column, so each INSERT recomputes the
timestamp. Existing row values are left untouched (their true creation time is
unrecoverable); only the column DEFAULT changes, fixing all future inserts.

The corresponding SQLAlchemy models are switched from ``server_default="now()"``
to ``server_default=text("now()")`` in the same change-set so a freshly built
database (or test schema created from metadata) never reintroduces the bug.

See specs/06-data-schema-api.md (timestamp columns are creation/update time).

Revision ID: e7f8a9b0c1d2
Revises: c4d5e6f7a8b9
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) pairs whose DEFAULT was frozen to a constant literal.
# Tables added via migrations that already used sa.text("now()")
# (llm_providers, llm_request_logs, llm_request_payloads, admin_payload_access)
# are intentionally excluded — their default is already a live now().
_FROZEN_TIMESTAMP_COLUMNS: tuple[tuple[str, str], ...] = (
    ("project", "created_at"),
    ("project", "updated_at"),
    ('"user"', "created_at"),
    ('"user"', "updated_at"),
    ("message", "created_at"),
    ("seat", "updated_at"),
    ("stage_history", "created_at"),
    ("stage_evaluation_log", "created_at"),
    ("micro_phase_history", "created_at"),
    ("agent_decision_trace", "created_at"),
)


def upgrade() -> None:
    for table, column in _FROZEN_TIMESTAMP_COLUMNS:
        op.execute(
            sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT now()")
        )


def downgrade() -> None:
    # The previous state was a bug (a frozen constant default). There is no
    # meaningful prior value to restore, so downgrade simply drops the default.
    for table, column in _FROZEN_TIMESTAMP_COLUMNS:
        op.execute(
            sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        )
