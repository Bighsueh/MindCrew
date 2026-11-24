import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
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
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_scenarios.id", ondelete="SET NULL"), index=True)
    scenario_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    note_body: Mapped[str | None] = mapped_column(Text)
    note_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


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


class InterviewPersona(Base):
    __tablename__ = "interview_personas"
    __table_args__ = (Index("ix_interview_personas_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    fields: Mapped[list[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

class InterviewScenario(Base):
    __tablename__ = "interview_scenarios"
    __table_args__ = (Index("ix_interview_scenarios_owner", "owner_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    profiles: Mapped[list[dict]] = mapped_column(JSONB)
    audience: Mapped[list[str]] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    generation_state: Mapped[str] = mapped_column(String(12))
    generation_error: Mapped[str | None] = mapped_column(String(32))
    generation_token: Mapped[uuid.UUID | None]
    generation_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    creation_signature: Mapped[str | None] = mapped_column(String(64))


class InterviewGuide(Base):
    __tablename__ = "interview_guides"
    __table_args__ = (Index("ix_interview_guides_owner_scenario", "owner_id", "scenario_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_scenarios.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class InterviewWorkspace(Base):
    __tablename__ = "interview_workspaces"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_scenarios.id", ondelete="CASCADE"), primary_key=True)
    note_body: Mapped[str | None] = mapped_column(Text)
    note_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    current_guide_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_guides.id", ondelete="SET NULL"))
