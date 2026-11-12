import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.config import get_settings
from app.days import is_valid_timezone, logical_day
from app.db import get_db
from app.models import Factor, Profile

router = APIRouter()


def ensure_profile(db: Session, user_id: uuid.UUID) -> Profile:
    """Create the profile on first contact. Safe under concurrent requests."""
    db.execute(insert(Profile).values(user_id=user_id).on_conflict_do_nothing())
    db.commit()
    return db.get(Profile, user_id)


def user_today(profile: Profile) -> date:
    return logical_day(datetime.now(timezone.utc), profile.timezone, get_settings().day_cutoff_hour)


def available_factors(db: Session, user_id: uuid.UUID) -> list[Factor]:
    """Global defaults plus this user's own factors."""
    return list(db.scalars(
        select(Factor)
        .where(Factor.active, or_(Factor.user_id.is_(None), Factor.user_id == user_id))
        .order_by(Factor.applies_to.desc(), Factor.sort_order)
    ))


class ProfileOut(BaseModel):
    user_id: uuid.UUID
    timezone: str
    today: date
    morning_reminder: time | None
    evening_reminder: time | None


class ProfileUpdate(BaseModel):
    """Only the fields you send are changed. Send a reminder as null to turn it off."""
    timezone: str | None = None
    morning_reminder: time | None = None
    evening_reminder: time | None = None


class FactorOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    value_type: str
    applies_to: str
    min_value: float | None
    max_value: float | None
    low_label: str | None
    high_label: str | None
    higher_is: str
    source: str
    detail_schema: list | None
    custom: bool


def _out(p: Profile) -> ProfileOut:
    return ProfileOut(
        user_id=p.user_id, timezone=p.timezone, today=user_today(p),
        morning_reminder=p.morning_reminder, evening_reminder=p.evening_reminder,
    )


@router.get("/me", response_model=ProfileOut)
def get_me(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    return _out(ensure_profile(db, user_id))


@router.patch("/me", response_model=ProfileOut)
def update_me(
    body: ProfileUpdate,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    p = ensure_profile(db, user_id)
    sent = body.model_fields_set

    if "timezone" in sent:
        if not body.timezone or not is_valid_timezone(body.timezone):
            raise HTTPException(422, f"Unknown timezone: {body.timezone}")
        p.timezone = body.timezone
    for kind in ("morning", "evening"):
        field = f"{kind}_reminder"
        if field in sent:
            setattr(p, field, getattr(body, field))
            # Changing the time re-arms today's reminder.
            setattr(p, f"last_{kind}_sent", None)

    db.commit()
    return _out(p)


@router.get("/factors", response_model=list[FactorOut])
def list_factors(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    return [
        FactorOut(
            id=f.id, key=f.key, label=f.label, value_type=f.value_type,
            applies_to=f.applies_to,
            min_value=float(f.min_value) if f.min_value is not None else None,
            max_value=float(f.max_value) if f.max_value is not None else None,
            low_label=f.low_label, high_label=f.high_label, higher_is=f.higher_is, source=f.source,
            detail_schema=f.detail_schema,
            custom=f.user_id is not None,
        )
        for f in available_factors(db, user_id)
    ]
