"""Phase 29: remove second diamond — backfill stale data

Revision ID: e0f1a2b3c4d5
Revises: d8e9f0a1b2c3
Create Date: 2026-05-26

Phase 29 縮減為強化版第一鑽石：
- current_stage / current_micro_phase 為 VARCHAR（非 PostgreSQL ENUM），
  schema 不需 alter type。
- 但既有 dev / staging data 可能存在 stage='develop'/'deliver' 或
  micro_phase='3.x'/'4.x' 的 project，code 在 Phase 29 後不再支援這些值。
- 本 migration 將這類 stale data 設為 status='archived' 並把 current_stage
  歸位 'completed'、current_micro_phase 歸位 '2.3'（第一鑽石終局）。

依據 spec/01-PRD.md §10「範圍邊界」、spec/04-06-micro-phase-state.md §4.10。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Archive any project that was in develop / deliver stage.
    #    These projects pre-date Phase 29 and cannot be advanced further
    #    under the first-diamond-only scope.
    op.execute(
        """
        UPDATE project
        SET status = 'archived',
            current_stage = 'completed',
            current_micro_phase = '2.3'
        WHERE current_stage IN ('develop', 'deliver')
           OR current_micro_phase LIKE '3.%%'
           OR current_micro_phase LIKE '4.%%'
        """
    )

    # 2. Defensive: also clean up any sub_phase that points into 3.x/4.x territory.
    op.execute(
        """
        UPDATE project
        SET current_sub_phase = NULL
        WHERE current_sub_phase LIKE '3.%%'
           OR current_sub_phase LIKE '4.%%'
        """
    )


def downgrade() -> None:
    # No-op downgrade: we cannot reconstruct which projects were originally
    # in develop / deliver. Phase 29 is intended to be irreversible via DB
    # migration; restoration requires git-history-level recovery of the
    # second-diamond code (see plan §10.3 of spec/01-PRD.md).
    pass
