"""SQLAlchemy model for llm_request_logs (Phase 25 + extension).

One row per LLM attempt (success or failure). Captures token usage, latency,
which tier actually served the request, and which tier the call cascaded from
if fallback happened.

Phase 25.J refinement: the original ``user_id`` was split into two concepts:
  * ``owning_user_id``  — NOT NULL. Who pays / who is attributed.
                          For agent ticks resolves to project.creator_id
                          (see app.llm.owning_user.resolve_owning_user).
  * ``triggered_by_user_id`` — nullable. Which human action triggered this
                          specific call (e.g. chat sender). NULL for autonomous
                          agent ticks.
Plus ``project_id`` so admin can filter by project context.

Full messages + response live in the side table ``llm_request_payloads``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMRequestLog(Base):
    __tablename__ = "llm_request_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    owning_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=False,
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    tier_used: Mapped[int] = mapped_column(Integer, nullable=False)
    cascade_from_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Phase 37: which quality pool actually served this request (quality/standard).
    capability_class_used: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    caller: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")

    __table_args__ = (
        Index("idx_llm_log_created_at", created_at.desc()),
        Index("idx_llm_log_provider_created", "provider_id", created_at.desc()),
        Index("idx_llm_log_owning_user_created", "owning_user_id", created_at.desc()),
        Index("idx_llm_log_project_created", "project_id", created_at.desc()),
    )
