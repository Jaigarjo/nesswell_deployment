"""Reminder settings on profiles + push_subscriptions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("morning_reminder", sa.Time))
    op.add_column("profiles", sa.Column("evening_reminder", sa.Time))
    op.add_column("profiles", sa.Column("last_morning_sent", sa.Date))
    op.add_column("profiles", sa.Column("last_evening_sent", sa.Date))

    op.create_table(
        "push_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.Text, nullable=False, unique=True),
        sa.Column("p256dh", sa.Text, nullable=False),
        sa.Column("auth", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    op.execute("""
    DO $$
    BEGIN
      IF to_regprocedure('auth.uid()') IS NOT NULL THEN
        ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;
        CREATE POLICY own_push_subscriptions ON push_subscriptions
          FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
      END IF;
    END $$;
    """)


def downgrade() -> None:
    op.drop_table("push_subscriptions")
    for col in ("last_evening_sent", "last_morning_sent", "evening_reminder", "morning_reminder"):
        op.drop_column("profiles", col)
