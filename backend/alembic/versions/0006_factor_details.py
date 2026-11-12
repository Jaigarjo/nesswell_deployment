"""Factor details: optional deeper fields and notes per factor per check-in.

Each factor carries a detail_schema (a list of field definitions). Values live in
entry_details as JSON, validated against that schema by the API. Adding or
changing fields later is a data change, not a code change.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-28
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def num(key, label, lo, hi, step=1, unit=None):
    return {"key": key, "label": label, "type": "number", "min": lo, "max": hi, "step": step, "unit": unit}


def choice(key, label, options):
    return {"key": key, "label": label, "type": "choice", "options": options}


def multi(key, label, options):
    return {"key": key, "label": label, "type": "multi", "options": options}


def tm(key, label):
    return {"key": key, "label": label, "type": "time"}


SCHEMAS = {
    "sleep_hours": [tm("bedtime", "Went to bed"), tm("wake", "Woke up"),
                    choice("nap", "Nap yesterday", ["None", "Short", "Long"])],
    "sleep_quality": [multi("disturbed", "What got in the way", [
        "Woke in the night", "Hard to fall asleep", "Woke too early", "Bad dreams", "Noise", "Too hot or cold"])],
    "exercise": [choice("type", "What you did", ["Run", "Gym", "Surf", "Swim", "Cycle", "Yoga", "Walk", "Team sport", "Other"]),
                 num("minutes", "How long", 0, 600, 5, "min"),
                 choice("intensity", "Intensity", ["Easy", "Moderate", "Hard"])],
    "social": [multi("who", "Who", ["Partner", "Friends", "Family", "Colleagues", "New people"]),
               choice("how", "How", ["In person", "Call or video", "Messages"]),
               choice("felt", "It felt", ["Energising", "Neutral", "Draining"])],
    "alcohol": [num("drinks", "Drinks", 0, 30, 1),
                multi("type", "Type", ["Beer", "Wine", "Spirits", "Cocktails", "Other"])],
    "work_stress": [num("hours", "Hours worked", 0, 24, 0.5, "h"),
                    multi("sources", "Where it came from", ["Deadlines", "Meetings", "Workload", "People", "Uncertainty", "Commute"])],
    "diet_quality": [choice("amount", "How much you ate", ["Too little", "About right", "Too much"]),
                     multi("food", "What you ate", ["Home-cooked", "Takeaway", "Fast food", "Fruit and veg",
                                                   "Protein", "Sweets", "Caffeine", "Processed"]),
                     num("meals", "Meals", 0, 10, 1)],
}


def upgrade() -> None:
    op.add_column("factors", sa.Column("detail_schema", JSONB))
    factors = sa.table("factors", sa.column("key"), sa.column("user_id"), sa.column("detail_schema", JSONB))
    for key, schema in SCHEMAS.items():
        op.execute(factors.update().where(factors.c.key == key, factors.c.user_id.is_(None))
                   .values(detail_schema=schema))

    op.create_table(
        "entry_details",
        sa.Column("entry_id", UUID(as_uuid=True), sa.ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("factor_id", UUID(as_uuid=True), sa.ForeignKey("factors.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("note", sa.Text),
        sa.Column("data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.execute("""
    DO $$
    BEGIN
      IF to_regprocedure('auth.uid()') IS NOT NULL THEN
        ALTER TABLE entry_details ENABLE ROW LEVEL SECURITY;
        CREATE POLICY own_entry_details ON entry_details
          FOR ALL USING (EXISTS (SELECT 1 FROM entries e WHERE e.id = entry_id AND e.user_id = auth.uid()));
      END IF;
    END $$;
    """)


def downgrade() -> None:
    op.drop_table("entry_details")
    op.drop_column("factors", "detail_schema")
