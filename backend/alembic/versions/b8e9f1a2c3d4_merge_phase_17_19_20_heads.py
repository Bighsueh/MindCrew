"""merge phase 17/19/20 heads

Revision ID: b8e9f1a2c3d4
Revises: 3b4c5d6e7f8a, a5c1f0b2e9d3, 20260511_1200
Create Date: 2026-05-11 02:00:00.000000

合併 4 個並行 worktree 的 3 個 alembic head：
- 3b4c5d6e7f8a (Phase 17 Stream B — timer_columns)
- a5c1f0b2e9d3 (Phase 19 — persona + constraints)
- 20260511_1200 (Phase 20 — chat_id_to_message)

Empty up/down — schema changes already applied by parent revisions.
詳見 prompts/phases/PHASE_MERGE_PLAN.md §3。
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b8e9f1a2c3d4"
down_revision: Union[str, Sequence[str], None] = (
    "3b4c5d6e7f8a",
    "a5c1f0b2e9d3",
    "20260511_1200",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op: this revision only collapses three parallel heads into one.
    pass


def downgrade() -> None:
    # No-op: downgrade is handled by individual parent revisions.
    pass
