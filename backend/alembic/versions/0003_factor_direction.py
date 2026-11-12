"""Factor direction: end labels for scales and whether higher is better.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# key: (low_label, high_label, higher_is)
DEFAULTS = {
    "sleep_hours":   (None, None, "better"),
    "sleep_quality": ("Poor", "Great", "better"),
    "exercise":      (None, None, "better"),
    "social":        (None, None, "better"),
    "alcohol":       (None, None, "worse"),
    "work_stress":   ("Calm", "Very stressed", "worse"),
    "diet_quality":  ("Badly", "Well", "better"),
}


def upgrade() -> None:
    op.add_column("factors", sa.Column("low_label", sa.String(64)))
    op.add_column("factors", sa.Column("high_label", sa.String(64)))
    op.add_column("factors", sa.Column("higher_is", sa.String(8), nullable=False, server_default="neutral"))
    op.create_check_constraint("ck_factors_higher_is", "factors", "higher_is IN ('better','worse','neutral')")
    factors = sa.table("factors", sa.column("key"), sa.column("user_id"),
                       sa.column("low_label"), sa.column("high_label"), sa.column("higher_is"))
    for key, (lo, hi, d) in DEFAULTS.items():
        op.execute(factors.update()
                   .where(factors.c.key == key, factors.c.user_id.is_(None))
                   .values(low_label=lo, high_label=hi, higher_is=d))


def downgrade() -> None:
    op.drop_constraint("ck_factors_higher_is", "factors")
    for col in ("higher_is", "high_label", "low_label"):
        op.drop_column("factors", col)
