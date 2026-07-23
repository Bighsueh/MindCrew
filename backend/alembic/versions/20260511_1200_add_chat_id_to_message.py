"""add_chat_id_to_message

新增 message.chat_id 欄位以支援個人聊天（DT 教練）。
詳見 chat_id 設計文件。

格式：
  - 群組：NULL（向下相容）或 "{project_id}:group"
  - 個人："{project_id}:personal:{user_id}"

本 migration **不做 data migration**——既有 row chat_id 保持 NULL，
由 helper / repository 視為 group。

Revision ID: 20260511_1200
Revises: 1fdee7446bf9
Create Date: 2026-05-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260511_1200"
down_revision: Union[str, Sequence[str], None] = "1fdee7446bf9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema：加 chat_id 欄位 + composite index。"""
    op.add_column(
        "message",
        sa.Column("chat_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "idx_message_project_chat_time",
        "message",
        ["project_id", "chat_id", sa.text("created_at DESC")],
        unique=False,
    )
    # 不做 data migration——既有 row chat_id 保持 NULL，helper 視為 group。


def downgrade() -> None:
    """Downgrade schema：移除 index + 移除欄位。"""
    op.drop_index("idx_message_project_chat_time", table_name="message")
    op.drop_column("message", "chat_id")
