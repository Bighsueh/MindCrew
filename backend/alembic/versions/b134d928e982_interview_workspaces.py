"""Add reusable interview scenarios, private workspaces and guides."""

from uuid import UUID

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b134d928e982"
down_revision = "a05e3757aaf2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    scenarios = op.create_table(
        "interview_scenarios",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("profiles", JSONB(), nullable=False),
        sa.Column("audience", JSONB(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation_state", sa.String(12), nullable=False),
        sa.Column("generation_error", sa.String(32)),
        sa.Column("generation_token", sa.Uuid()),
        sa.Column("generation_until", sa.DateTime(timezone=True)),
        sa.Column("creation_signature", sa.String(64)),
    )
    op.create_index("ix_interview_scenarios_owner", "interview_scenarios", ["owner_id"])
    op.execute(scenarios.insert().values(
        id=UUID("aa99a07d-014c-40bf-af36-4778d2b25edd"),
        kind="preset", title="校園公共學習空間",
        description="如何改善大學生使用校園公共學習空間的體驗？空間含靠窗插座座位、討論桌與走道。",
        profiles=sa.literal_column("'[]'::jsonb"), audience=sa.literal_column("'[]'::jsonb"),
        created_at=sa.func.now(), generation_state="ready",
    ))
    op.add_column("interview_sessions", sa.Column("scenario_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_interview_sessions_scenario", "interview_sessions", "interview_scenarios",
        ["scenario_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_interview_sessions_scenario_id", "interview_sessions", ["scenario_id"])
    op.execute(
        """UPDATE interview_sessions
           SET scenario_id = 'aa99a07d-014c-40bf-af36-4778d2b25edd'
           WHERE COALESCE(scenario_snapshot->'scenario'->>'kind', 'preset') = 'preset'"""
    )
    op.execute(
        """INSERT INTO interview_scenarios
              (id, owner_id, kind, title, description, profiles, audience, created_at, generation_state)
           SELECT id, owner_id, 'custom', scenario_snapshot->'scenario'->>'title',
                  scenario_snapshot->'scenario'->>'description', '[]'::jsonb, '[]'::jsonb, started_at, 'pending'
           FROM interview_sessions WHERE scenario_snapshot->'scenario'->>'kind' = 'custom'"""
    )
    op.execute(
        """UPDATE interview_sessions SET scenario_id = id
           WHERE scenario_snapshot->'scenario'->>'kind' = 'custom'"""
    )
    op.create_table(
        "interview_guides",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), sa.ForeignKey("interview_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interview_guides_owner_scenario", "interview_guides", ["owner_id", "scenario_id"])
    op.create_table(
        "interview_workspaces",
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("scenario_id", sa.Uuid(), sa.ForeignKey("interview_scenarios.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("note_body", sa.Text()),
        sa.Column("note_updated_at", sa.DateTime(timezone=True)),
        sa.Column("current_guide_id", sa.Uuid(), sa.ForeignKey("interview_guides.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    op.drop_table("interview_workspaces")
    op.drop_table("interview_guides")
    op.drop_index("ix_interview_sessions_scenario_id", table_name="interview_sessions")
    op.drop_constraint("fk_interview_sessions_scenario", "interview_sessions", type_="foreignkey")
    op.drop_column("interview_sessions", "scenario_id")
    op.drop_table("interview_scenarios")
