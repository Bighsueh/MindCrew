import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Text, ForeignKey, Index, Integer, text
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
        String(20), nullable=False, default="warmup"
    )
    current_micro_phase: Mapped[str] = mapped_column(
        String(10), nullable=False, default="0.0"
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
    # Phase 28:三模式輪流規則（cued / round_robin / open_floor）。
    # persona 決定「講什麼」，turn_policy 決定「誰講」。預設 cued 維持既有行為。
    turn_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="cued", server_default="cued"
    )
    # Phase 28：人類被 cue 的單次 timeout 秒數（10-600，預設 180）
    cue_timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=180, server_default="180"
    )
    # Phase 28：cue timeout 後 supervisor 最多 reminder 次數（0-10，預設 5；0=不 retry）
    cue_max_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    # Phase 30: DEMO 導覽完成記錄（{user_id: ISO8601 timestamp}）
    # 進入 workspace 時若該 user 不在此 map，前端顯示 0.1 DEMO 導覽 + 自動寫入。
    tour_acknowledged_by: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    # Phase 34: 第一鑽石終局產出（JSONB），由 closing ritual 在 stage 進 'completed'
    # 時寫入。結構：{personas, chosen_problem_statement, chosen_hmw, completed_at, summary}
    first_diamond_output: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_project_creator", "creator_id"),
        Index("idx_project_status", "status"),
        Index("idx_project_linked_teacher", "linked_teacher_id"),
    )
