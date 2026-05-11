import uuid
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from app.db.base import Base


class Message(Base):
    __tablename__ = "message"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String(10), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    # chat_id：群組訊息為 NULL 或 "{project_id}:group"；個人訊息為 "{project_id}:personal:{user_id}"。
    # 詳見 specs/13-personal-chat.md §4.3。索引由下方 composite index 處理。
    chat_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        Index("idx_message_project", "project_id"),
        Index("idx_message_project_time", "project_id", created_at.desc()),
        Index(
            "idx_message_project_chat_time",
            "project_id",
            "chat_id",
            created_at.desc(),
        ),
    )
