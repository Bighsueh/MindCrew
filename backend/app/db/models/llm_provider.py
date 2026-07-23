"""SQLAlchemy model for llm_providers (Phase 25).

Stores per-provider config (tier, kind, base_url, model, credentials). The
provider registry reads this table at startup and after admin edits to build
the in-memory tier buckets used by ``LLMRouter``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMProvider(Base):
    __tablename__ = "llm_providers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    # Phase 37: quality pool, orthogonal to tier. 'quality' = strong-but-slow,
    # 'standard' = fast default. Routing key resolved from caller (routing_policy).
    capability_class: Mapped[str] = mapped_column(
        String(16), nullable=False, default="standard", server_default="standard"
    )
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    azure_api_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    azure_deployment: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("tier BETWEEN 1 AND 5", name="ck_llm_provider_tier_range"),
        CheckConstraint(
            "kind IN ('vllm', 'azure_openai')", name="ck_llm_provider_kind"
        ),
        CheckConstraint(
            "capability_class IN ('quality', 'standard')",
            name="ck_llm_provider_capability_class",
        ),
        Index("idx_llm_provider_tier_enabled", "tier", "enabled"),
        Index("idx_llm_provider_class_enabled", "capability_class", "enabled"),
    )
