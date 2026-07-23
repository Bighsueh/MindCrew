import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, ForeignKey, Index, text
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
    # 詳。索引由下方 composite index 處理。
    chat_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    # app 端 default callable：每筆 insert 由 SQLAlchemy 帶入正確當下時間，
    # 不依賴 DB server_default（既有 schema 的預設值被凍結成固定字面值，
    # 會導致所有 row created_at 相同，破壞時間軸 / 教師決策回放）。
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
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
