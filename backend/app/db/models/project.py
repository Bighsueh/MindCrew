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
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 27：建立時使用者勾選的利害關係人；shape: list[{id, name, role, relevance, selected}]
    stakeholders: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # Phase 27：'open' = Phase 27 後 open brief 流程；'legacy' = 之前的資料
    task_brief_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="legacy", server_default="legacy"
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    # Phase 22：活動邀請碼（教師輸入此碼即可列管該活動）+ 已列管的教師
    invite_code: Mapped[str] = mapped_column(
        String(8), unique=True, nullable=False, index=True
    )
    linked_teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
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
        Index("idx_project_linked_teacher", "linked_teacher_id"),
    )
