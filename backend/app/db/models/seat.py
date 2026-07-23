import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB

from app.db.base import Base

# ── Seat role / state / occupant constants（單一真理來源，跨 service 與 manager 共用）──
SEAT_ROLE_SUPERVISOR = "supervisor"
# 真人專屬席：額外 +1，綁定專案 creator，crew_* 永遠是常駐 AI、不可被真人頂替。
SEAT_ROLE_HUMAN_CREATOR = "human_creator"

OCCUPANT_AI = "ai"
OCCUPANT_HUMAN = "human"

SEAT_STATE_DORMANT = "dormant"          # AI 席尚未啟動（第一位真人入座前）
SEAT_STATE_AI_RUNNING = "ai_running"    # AI agent 運行中
SEAT_STATE_HUMAN_ACTIVE = "human_active"  # 真人在座
SEAT_STATE_VACANT = "vacant"            # 真人專屬席空置（creator 尚未入座／已離開）


class Seat(Base):
    __tablename__ = "seat"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    seat_role: Mapped[str] = mapped_column(String(20), nullable=False)
    occupant_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ai"
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ai_running"
    )
    persona: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Phase 22：席位首次發訊息／貼便利貼時鎖定，往後該席位的氣泡與便利貼預設色都用這個
    sticky_color: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("project_id", "seat_role"),
        Index("idx_seat_project", "project_id"),
    )
