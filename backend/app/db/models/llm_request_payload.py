"""SQLAlchemy model for llm_request_payloads (Phase 25 extension).

Cold table: full messages + response for replay/audit. 1:1 with
llm_request_logs (the log id is the payload PK). Kept separate from the hot
log table because payloads can be megabytes and stats queries scan the log
table frequently.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMRequestPayload(Base):
    __tablename__ = "llm_request_payloads"

    request_log_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("llm_request_logs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    messages: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    response_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_finish_reason: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    messages_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("idx_llm_payload_created_at", created_at.desc()),)
