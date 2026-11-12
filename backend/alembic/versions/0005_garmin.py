"""Garmin: encrypted connections, synced daily metrics, device factors.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# key, label, applies_to, min, max, higher_is, action, sort
# Morning metrics describe the night before; evening ones describe the day.
GARMIN_FACTORS = [
    ("g_sleep_hours",   "Sleep (Garmin)",        "morning", 0, 16,     "neutral", None, 10),
    ("g_sleep_score",   "Sleep score",           "morning", 0, 100,    "neutral", None, 11),
    ("g_hrv",           "Overnight HRV",         "morning", 0, 300,    "neutral", None, 12),
    ("g_resting_hr",    "Resting heart rate",    "morning", 20, 150,   "neutral", None, 13),
    ("g_body_battery",  "Body Battery at wake",  "morning", 0, 100,    "neutral", None, 14),
    ("g_stress",        "Average stress",        "evening", 0, 100,    "neutral", None, 10),
    ("g_steps",         "Steps",                 "evening", 0, 100000, "better",  "Walk {good} steps", 11),
]


def upgrade() -> None:
    op.add_column("factors", sa.Column("source", sa.String(8), nullable=False, server_default="manual"))
    factors = sa.table("factors", sa.column("key"), sa.column("label"), sa.column("value_type"),
                       sa.column("applies_to"), sa.column("min_value"), sa.column("max_value"),
                       sa.column("higher_is"), sa.column("action"), sa.column("sort_order"), sa.column("source"))
    op.bulk_insert(factors, [
        dict(key=k, label=l, value_type="number", applies_to=a, min_value=lo, max_value=hi,
             higher_is=d, action=act, sort_order=s, source="garmin")
        for k, l, a, lo, hi, d, act, s in GARMIN_FACTORS
    ])

    op.create_table(
        "garmin_connections",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tokens_enc", sa.Text, nullable=False),          # Fernet-encrypted token JSON
        sa.Column("status", sa.String(10), nullable=False, server_default="connected"),  # connected | reauth
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "daily_metrics",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Numeric, nullable=False),
    )

    op.execute("""
    DO $$
    BEGIN
      IF to_regprocedure('auth.uid()') IS NOT NULL THEN
        -- Tokens are only ever touched by the API; no Data API policy at all.
        ALTER TABLE garmin_connections ENABLE ROW LEVEL SECURITY;
        ALTER TABLE daily_metrics ENABLE ROW LEVEL SECURITY;
        CREATE POLICY own_daily_metrics ON daily_metrics
          FOR SELECT USING (user_id = auth.uid());
      END IF;
    END $$;
    """)


def downgrade() -> None:
    op.drop_table("daily_metrics")
    op.drop_table("garmin_connections")
    op.execute("DELETE FROM factors WHERE source = 'garmin'")
    op.drop_column("factors", "source")
