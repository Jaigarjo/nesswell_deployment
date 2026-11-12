"""Initial schema: profiles, entries, factors, factor_values + default factors.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLES = ("profiles", "entries", "factors", "factor_values")

# key, label, value_type, applies_to, min, max, sort_order
DEFAULT_FACTORS = [
    ("sleep_hours",   "Hours slept",       "number", "morning", 0, 16, 1),
    ("sleep_quality", "Sleep quality",     "scale",  "morning", 1, 5,  2),
    ("exercise",      "Worked out",        "bool",   "evening", 0, 1,  1),
    ("social",        "Saw people",        "bool",   "evening", 0, 1,  2),
    ("alcohol",       "Drank alcohol",     "bool",   "evening", 0, 1,  3),
    ("work_stress",   "Work stress",       "scale",  "evening", 1, 5,  4),
    ("diet_quality",  "How well I ate",    "scale",  "evening", 1, 5,  5),
]


def upgrade() -> None:
    uuid_pk = lambda: sa.Column("id", UUID(as_uuid=True), primary_key=True,
                                server_default=sa.text("gen_random_uuid()"))

    op.create_table(
        "profiles",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "entries",
        uuid_pk(),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "day", "kind", name="uq_entries_user_day_kind"),
        sa.CheckConstraint("kind IN ('morning','evening')", name="ck_entries_kind"),
        sa.CheckConstraint("score BETWEEN 1 AND 10", name="ck_entries_score"),
    )
    op.create_index("ix_entries_user_day", "entries", ["user_id", "day"])

    op.create_table(
        "factors",
        uuid_pk(),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("profiles.user_id", ondelete="CASCADE")),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("value_type", sa.String(8), nullable=False),
        sa.Column("applies_to", sa.String(8), nullable=False),
        sa.Column("min_value", sa.Numeric),
        sa.Column("max_value", sa.Numeric),
        sa.Column("sort_order", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.CheckConstraint("value_type IN ('bool','number','scale')", name="ck_factors_type"),
        sa.CheckConstraint("applies_to IN ('morning','evening')", name="ck_factors_applies"),
    )
    op.create_index("uq_factors_global_key", "factors", ["key"], unique=True,
                    postgresql_where=sa.text("user_id IS NULL"))
    op.create_index("uq_factors_user_key", "factors", ["user_id", "key"], unique=True,
                    postgresql_where=sa.text("user_id IS NOT NULL"))

    op.create_table(
        "factor_values",
        sa.Column("entry_id", UUID(as_uuid=True),
                  sa.ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("factor_id", UUID(as_uuid=True),
                  sa.ForeignKey("factors.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("value", sa.Numeric, nullable=False),
    )

    factors = sa.table(
        "factors",
        sa.column("key"), sa.column("label"), sa.column("value_type"),
        sa.column("applies_to"), sa.column("min_value"), sa.column("max_value"),
        sa.column("sort_order"),
    )
    op.bulk_insert(factors, [
        dict(zip(["key", "label", "value_type", "applies_to",
                  "min_value", "max_value", "sort_order"], row))
        for row in DEFAULT_FACTORS
    ])

    # Supabase-only hardening. Skipped automatically on plain Postgres (local dev/tests).
    #  1. Deleting a Supabase auth user deletes all their data.
    #  2. RLS on every table. Supabase exposes the public schema through its Data API,
    #     so without this anyone with the anon key could read other users' logs.
    #     The FastAPI backend connects as the table owner, which bypasses RLS,
    #     so the API still filters by user_id itself.
    op.execute("""
    DO $$
    BEGIN
      IF to_regprocedure('auth.uid()') IS NOT NULL THEN
        ALTER TABLE profiles ADD CONSTRAINT fk_profiles_auth_user
          FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

        ALTER TABLE profiles      ENABLE ROW LEVEL SECURITY;
        ALTER TABLE entries       ENABLE ROW LEVEL SECURITY;
        ALTER TABLE factors       ENABLE ROW LEVEL SECURITY;
        ALTER TABLE factor_values ENABLE ROW LEVEL SECURITY;

        CREATE POLICY own_profile ON profiles
          FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
        CREATE POLICY own_entries ON entries
          FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
        CREATE POLICY read_factors ON factors
          FOR SELECT USING (user_id IS NULL OR user_id = auth.uid());
        CREATE POLICY own_factor_values ON factor_values
          FOR ALL USING (EXISTS (SELECT 1 FROM entries e
                                 WHERE e.id = entry_id AND e.user_id = auth.uid()));
      END IF;
    END $$;
    """)


def downgrade() -> None:
    for t in reversed(TABLES):
        op.drop_table(t)
