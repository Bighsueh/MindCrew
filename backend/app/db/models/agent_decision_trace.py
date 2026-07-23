import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB

from app.db.base import Base


class AgentDecisionTrace(Base):
    __tablename__ = "agent_decision_trace"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    micro_phase: Mapped[str | None] = mapped_column(String(10), nullable=True)
    role_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ASSESS phase
    assess_result: Mapped[str] = mapped_column(String(20), nullable=False)
    assess_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assess_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Think phase
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Act phase
    action_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    action_result: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # app 端 default callable：每筆 insert 帶入正確當下時間，不依賴被凍結的
    # DB server_default（否則所有 trace created_at 相同，時間軸無法重建）。
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("idx_trace_project", "project_id"),
        Index("idx_trace_project_time", "project_id", created_at.desc()),
        Index("idx_trace_agent", "agent_id", created_at.desc()),
    )
