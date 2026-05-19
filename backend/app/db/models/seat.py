import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB

from app.db.base import Base


class Seat(Base):
    __tablename__ = "seat"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    seat_role: Mapped[str] = mapped_column(String(20), nullable=False)
    occupant_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ai"
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ai_running"
    )
    persona: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Phase 22：席位首次發訊息／貼便利貼時鎖定，往後該席位的氣泡與便利貼預設色都用這個
    sticky_color: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        UniqueConstraint("project_id", "seat_role"),
        Index("idx_seat_project", "project_id"),
    )
