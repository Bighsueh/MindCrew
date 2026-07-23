"""Phase 42 C1：第一鑽石 5＋7 格重構——舊 micro/sub 值就近映射 backfill。

Revision ID: a1b2c3d4e5a6
Revises: f6a7b8c9d0e1
Create Date: 2026-06-13

Context（spec 22 v2.0 §11.1）
-----------------------------
sub-phase 結構改為 0.0a → 1.1a–1.1d、1.2 → 2.1–2.7（0.1/0.2 與 1.3–1.6 正式移除）；
micro 改 6 桶（0.0/1.1/1.2/2.1/2.2/2.3，0.1/0.2/1.3 移除）。既有專案的
``current_sub_phase``／``current_micro_phase``／``current_stage`` 依「移除值一律
映射到順序上最近的存續格」backfill：

  - sub 0.1 / 0.2        → 1.1a（micro→1.1、stage→discover）
  - sub 1.3 / 1.4 / 1.5  → 1.2 （micro→1.2、stage→discover）
  - sub 1.6              → 2.1 （micro→2.1、stage→define——舊資料已按舊規則
                                 過 1.5 硬閘，視為完成發現階段）
  - 其餘 sub 值不變（id 沿用；1.1d/1.2 語意整格抽換不影響資料）
  - 僅 micro 有舊值（sub 為 NULL）：micro 0.1/0.2 → 1.1、micro 1.3 → 2.1（stage 同步）

舊 ``scope_rationale``／``raw_observation`` 便條保留為歷史資料、不再參與任何 gate
（spec 22 v2.0 §11.1）。``agent_decision_trace`` 的歷史 sub_phase 值不改寫（追溯用）。

Downgrade：no-op（資料映射不可逆——舊值已無對應格定義可還原）。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5a6"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) sub-phase 為主的映射（micro / stage 隨映射後 sub 同步重算）。
    op.execute(
        """
        UPDATE project
        SET current_sub_phase = '1.1a',
            current_micro_phase = '1.1',
            current_stage = 'discover'
        WHERE current_sub_phase IN ('0.1', '0.2')
        """
    )
    op.execute(
        """
        UPDATE project
        SET current_sub_phase = '1.2',
            current_micro_phase = '1.2',
            current_stage = 'discover'
        WHERE current_sub_phase IN ('1.3', '1.4', '1.5')
        """
    )
    op.execute(
        """
        UPDATE project
        SET current_sub_phase = '2.1',
            current_micro_phase = '2.1',
            current_stage = 'define'
        WHERE current_sub_phase = '1.6'
        """
    )

    # 2) sub 為 NULL、僅 micro 殘留舊值的專案（macro-stage-only 模式向下相容）。
    op.execute(
        """
        UPDATE project
        SET current_micro_phase = '1.1',
            current_stage = 'discover'
        WHERE current_sub_phase IS NULL
          AND current_micro_phase IN ('0.1', '0.2')
        """
    )
    op.execute(
        """
        UPDATE project
        SET current_micro_phase = '2.1',
            current_stage = 'define'
        WHERE current_sub_phase IS NULL
          AND current_micro_phase = '1.3'
        """
    )

    # 3) 防禦性一致化：存續 sub 值但 micro 仍是移除桶（理論上不該發生——
    #    sub 1.1a–1.1d 配 micro 1.1、sub 1.2 配 micro 1.2；desync 舊資料兜底）。
    op.execute(
        """
        UPDATE project
        SET current_micro_phase = '1.1'
        WHERE current_sub_phase IN ('1.1a', '1.1b', '1.1c', '1.1d')
          AND current_micro_phase IN ('0.1', '0.2', '1.3')
        """
    )
    op.execute(
        """
        UPDATE project
        SET current_micro_phase = '1.2'
        WHERE current_sub_phase = '1.2'
          AND current_micro_phase IN ('0.1', '0.2', '1.3')
        """
    )


def downgrade() -> None:
    # 資料映射不可逆（移除格已無定義）；保留為 no-op。
    pass
