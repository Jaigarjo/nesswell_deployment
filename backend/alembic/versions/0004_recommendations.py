"""Recommendations: per-factor action text + experiments.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# "{good}" is filled with the helpful side of the split, e.g. "7+" or "below 3".
ACTIONS = {
    "sleep_hours":   "Get {good} hours of sleep",
    "sleep_quality": "Aim for good sleep ({good} out of 5)",
    "exercise":      "Get some exercise",
    "social":        "See people",
    "alcohol":       "Skip alcohol",
    "work_stress":   "Keep work stress {good}",
    "diet_quality":  "Eat well ({good} out of 5)",
}


def upgrade() -> None:
    op.add_column("factors", sa.Column("action", sa.String(128)))
    factors = sa.table("factors", sa.column("key"), sa.column("user_id"), sa.column("action"))
    for key, text in ACTIONS.items():
        op.execute(factors.update().where(factors.c.key == key, factors.c.user_id.is_(None)).values(action=text))

    op.create_table(
        "experiments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factor_id", UUID(as_uuid=True), sa.ForeignKey("factors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target", sa.String(8), nullable=False),       # morning | evening | daily
        sa.Column("lag", sa.SmallInteger, nullable=False),        # 0 same day, 1 next day
        sa.Column("op", sa.String(2), nullable=False),            # eq | ge | gt | lt | le
        sa.Column("threshold", sa.Numeric, nullable=False),
        sa.Column("action", sa.String(160), nullable=False),      # text shown to the user
        sa.Column("start_day", sa.Date, nullable=False),
        sa.Column("end_day", sa.Date, nullable=False),
        sa.Column("goal_days", sa.SmallInteger, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("finished_notified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active','completed','cancelled')", name="ck_experiments_status"),
        sa.CheckConstraint("op IN ('eq','ge','gt','lt','le')", name="ck_experiments_op"),
        sa.CheckConstraint("target IN ('morning','evening','daily')", name="ck_experiments_target"),
    )
    op.create_index("ix_experiments_user", "experiments", ["user_id", "created_at"])
    # At most one running experiment per person.
    op.create_index("uq_experiments_one_active", "experiments", ["user_id"], unique=True,
                    postgresql_where=sa.text("status = 'active'"))

    op.execute("""
    DO $$
    BEGIN
      IF to_regprocedure('auth.uid()') IS NOT NULL THEN
        ALTER TABLE experiments ENABLE ROW LEVEL SECURITY;
        CREATE POLICY own_experiments ON experiments
          FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
      END IF;
    END $$;
    """)


def downgrade() -> None:
    op.drop_table("experiments")
    op.drop_column("factors", "action")
