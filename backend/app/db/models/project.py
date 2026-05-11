import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB

from app.db.base import Base


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    current_stage: Mapped[str] = mapped_column(
        String(20), nullable=False, default="discover"
    )
    current_micro_phase: Mapped[str] = mapped_column(
        String(10), nullable=False, default="1.1"
    )
    # Spec 13: Sticky-Only Strategy sub-phase（向下相容：None 表示沿用 micro_phase 邏輯）
    current_sub_phase: Mapped[str | None] = mapped_column(
        String(8), nullable=True, default=None
    )
    # Spec 15: Timer 系統（None = 使用 default 2hr preset）
    timer_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    timer_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    ai_contribution: Mapped[str] = mapped_column(
        String(10), nullable=False, default="medium"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        Index("idx_project_creator", "creator_id"),
        Index("idx_project_status", "status"),
    )
