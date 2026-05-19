"""Phase 22: enrollment codes (teacher signature, project invite) + seat sticky color

Revision ID: c1d2e3f4a5b6
Revises: b8e9f1a2c3d4
Create Date: 2026-05-19
"""
import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b8e9f1a2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 與 app/auth/codes.py 同步：去掉容易混淆的字（0/O/1/I/L）
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _short_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def upgrade() -> None:
    bind = op.get_bind()

    # ── user.signature_code ──────────────────────────────────────────────
    op.add_column(
        "user",
        sa.Column("signature_code", sa.String(length=8), nullable=True),
    )
    op.create_unique_constraint("uq_user_signature_code", "user", ["signature_code"])

    # backfill：所有現有 teacher 補一個 code
    teacher_rows = bind.execute(
        sa.text("SELECT id FROM \"user\" WHERE role = 'teacher'")
    ).fetchall()
    used: set[str] = set()
    for (uid,) in teacher_rows:
        while True:
            code = _short_code()
            if code in used:
                continue
            exists = bind.execute(
                sa.text('SELECT 1 FROM "user" WHERE signature_code = :c'),
                {"c": code},
            ).first()
            if exists:
                continue
            used.add(code)
            break
        bind.execute(
            sa.text('UPDATE "user" SET signature_code = :c WHERE id = :id'),
            {"c": code, "id": uid},
        )

    # ── project.invite_code + linked_teacher_id ──────────────────────────
    op.add_column(
        "project",
        sa.Column("invite_code", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "project",
        sa.Column(
            "linked_teacher_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=True,
        ),
    )

    project_rows = bind.execute(sa.text("SELECT id FROM project")).fetchall()
    used.clear()
    for (pid,) in project_rows:
        while True:
            code = _short_code()
            if code in used:
                continue
            exists = bind.execute(
                sa.text("SELECT 1 FROM project WHERE invite_code = :c"),
                {"c": code},
            ).first()
            if exists:
                continue
            used.add(code)
            break
        bind.execute(
            sa.text("UPDATE project SET invite_code = :c WHERE id = :id"),
            {"c": code, "id": pid},
        )

    op.alter_column("project", "invite_code", nullable=False)
    op.create_unique_constraint("uq_project_invite_code", "project", ["invite_code"])
    op.create_index("idx_project_invite_code", "project", ["invite_code"])
    op.create_index(
        "idx_project_linked_teacher", "project", ["linked_teacher_id"]
    )

    # ── seat.sticky_color ────────────────────────────────────────────────
    op.add_column(
        "seat",
        sa.Column("sticky_color", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("seat", "sticky_color")
    op.drop_index("idx_project_linked_teacher", table_name="project")
    op.drop_index("idx_project_invite_code", table_name="project")
    op.drop_constraint("uq_project_invite_code", "project", type_="unique")
    op.drop_column("project", "linked_teacher_id")
    op.drop_column("project", "invite_code")
    op.drop_constraint("uq_user_signature_code", "user", type_="unique")
    op.drop_column("user", "signature_code")
