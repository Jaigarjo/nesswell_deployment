import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric,
    SmallInteger, String, Text, Time, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Profile(Base):
    """One row per user. user_id is the Supabase auth user id (the JWT 'sub')."""
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default="UTC")
    # Local reminder times; NULL = reminder off.
    morning_reminder: Mapped[time | None] = mapped_column(Time)
    evening_reminder: Mapped[time | None] = mapped_column(Time)
    # Logical day a reminder was last sent, so each fires at most once a day.
    last_morning_sent: Mapped[date | None] = mapped_column(Date)
    last_evening_sent: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Entry(Base):
    """One check-in. At most one morning and one evening per user per logical day."""
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint("user_id", "day", "kind", name="uq_entries_user_day_kind"),
        CheckConstraint("kind IN ('morning','evening')", name="ck_entries_kind"),
        CheckConstraint("score BETWEEN 1 AND 10", name="ck_entries_score"),
        Index("ix_entries_user_day", "user_id", "day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE")
    )
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(8))
    score: Mapped[int] = mapped_column(SmallInteger)
    note: Mapped[str | None] = mapped_column(Text)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    values: Mapped[list["FactorValue"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )
    details: Mapped[list["EntryDetail"]] = relationship(cascade="all, delete-orphan")


class Factor(Base):
    """Something that can be logged. user_id NULL = global default; set = a user's custom factor."""
    __tablename__ = "factors"
    __table_args__ = (
        CheckConstraint("value_type IN ('bool','number','scale')", name="ck_factors_type"),
        CheckConstraint("applies_to IN ('morning','evening')", name="ck_factors_applies"),
        CheckConstraint("higher_is IN ('better','worse','neutral')", name="ck_factors_higher_is"),
        Index("uq_factors_global_key", "key", unique=True,
              postgresql_where=text("user_id IS NULL")),
        Index("uq_factors_user_key", "user_id", "key", unique=True,
              postgresql_where=text("user_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    value_type: Mapped[str] = mapped_column(String(8))
    applies_to: Mapped[str] = mapped_column(String(8))
    min_value: Mapped[Decimal | None] = mapped_column(Numeric)
    max_value: Mapped[Decimal | None] = mapped_column(Numeric)
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    # Direction: what the ends of a scale mean, and whether more is good for you.
    low_label: Mapped[str | None] = mapped_column(String(64))
    high_label: Mapped[str | None] = mapped_column(String(64))
    higher_is: Mapped[str] = mapped_column(String(8), server_default="neutral")
    action: Mapped[str | None] = mapped_column(String(128))  # e.g. "Get {good} hours of sleep"
    source: Mapped[str] = mapped_column(String(8), server_default="manual")  # manual | garmin
    detail_schema: Mapped[list | None] = mapped_column(JSONB)  # optional deeper fields
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class FactorValue(Base):
    """Long-format values. Bools stored as 0/1 so everything pivots into one numeric matrix."""
    __tablename__ = "factor_values"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    factor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factors.id", ondelete="CASCADE"), primary_key=True
    )
    value: Mapped[Decimal] = mapped_column(Numeric)

    entry: Mapped[Entry] = relationship(back_populates="values")
    factor: Mapped[Factor] = relationship()


class PushSubscription(Base):
    """A browser/device that accepted push notifications. One user can have several."""
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Experiment(Base):
    """'Try X on N of the next 7 days', scored against the mood it's meant to move."""
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE")
    )
    factor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factors.id", ondelete="CASCADE")
    )
    target: Mapped[str] = mapped_column(String(8))
    lag: Mapped[int] = mapped_column(SmallInteger)
    op: Mapped[str] = mapped_column(String(2))
    threshold: Mapped[Decimal] = mapped_column(Numeric)
    action: Mapped[str] = mapped_column(String(160))
    start_day: Mapped[date] = mapped_column(Date)
    end_day: Mapped[date] = mapped_column(Date)
    goal_days: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(10), server_default="active")
    finished_notified: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    factor: Mapped[Factor] = relationship()


class GarminConnection(Base):
    """One per user. Only encrypted tokens are stored, never the Garmin password."""
    __tablename__ = "garmin_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE"), primary_key=True
    )
    tokens_enc: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), server_default="connected")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyMetric(Base):
    """A synced device value for a day, e.g. (user, 2026-09-28, 'g_hrv', 52)."""
    __tablename__ = "daily_metrics"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric)


class EntryDetail(Base):
    """The deeper layer for one factor in one check-in: structured fields plus a note."""
    __tablename__ = "entry_details"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    factor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factors.id", ondelete="CASCADE"), primary_key=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    factor: Mapped[Factor] = relationship()
