import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB

from app.db.base import Base


class MicroPhaseHistory(Base):
    __tablename__ = "micro_phase_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    from_micro_phase: Mapped[str] = mapped_column(String(10), nullable=False)
    to_micro_phase: Mapped[str] = mapped_column(String(10), nullable=False)
    transition_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="advance"
    )
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    canvas_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_micro_phase_history_project", "project_id"),
    )
