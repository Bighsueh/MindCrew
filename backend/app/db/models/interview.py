import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (Index("ix_interview_sessions_owner_started", "owner_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    stakeholder_id: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class InterviewExchange(Base):
    __tablename__ = "interview_exchanges"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_interview_exchange_sequence"),
        UniqueConstraint("session_id", "request_id", name="uq_interview_exchange_request"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"))
    sequence: Mapped[int]
    request_id: Mapped[uuid.UUID]
    question: Mapped[str] = mapped_column(Text)
    asked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12))
    error_code: Mapped[str | None] = mapped_column(String(32))
    attempt_count: Mapped[int] = mapped_column(default=0)
    attempt_token: Mapped[uuid.UUID | None]
    # Generation deadline while waiting, earliest retry time after a rate limit.
    waiting_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
