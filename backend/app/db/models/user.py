import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from app.db.base import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="student"
    )
    can_create_project: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Phase 22：教師簽名碼，學生於建立活動時輸入此碼即可被該教師列管
    signature_code: Mapped[str | None] = mapped_column(
        String(8), unique=True, nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    creator: Mapped["User | None"] = relationship(
        "User", remote_side="User.id", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_created_by", "created_by"),
    )
