"""SQLAlchemy model for admin_payload_access (Phase 25 extension).

Audit log: every admin open of a log detail modal (which exposes the raw
prompt + response, potentially containing student PII) writes one row here so
the team can later answer "which admin viewed which student's content?".
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminPayloadAccess(Base):
    __tablename__ = "admin_payload_access"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_log_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("llm_request_logs.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_admin_payload_access_admin", "admin_user_id", created_at.desc()),
        Index("idx_admin_payload_access_log", "request_log_id"),
    )
