import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.auth import current_user_id
from app.db import get_db
from app.models import Entry, EntryDetail, Factor, FactorValue
from app.profiles import available_factors, ensure_profile, user_today

router = APIRouter(prefix="/entries")

Kind = Literal["morning", "evening"]
EARLIEST_DAY = date(2000, 1, 1)


class DetailIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
    data: dict[str, Any] = Field(default_factory=dict)


class EntryIn(BaseModel):
    score: int = Field(ge=1, le=10)
    note: str | None = Field(default=None, max_length=2000)
    values: dict[str, float] = Field(default_factory=dict)
    # Optional deeper layer per factor: {"exercise": {"note": "...", "data": {"type": "Run", "minutes": 30}}}
    details: dict[str, DetailIn] = Field(default_factory=dict)


class EntryOut(BaseModel):
    day: date
    kind: Kind
    score: int
    note: str | None
    logged_at: datetime
    values: dict[str, float]
    details: dict[str, DetailIn]


def _to_out(e: Entry) -> EntryOut:
    return EntryOut(
        day=e.day, kind=e.kind, score=e.score, note=e.note, logged_at=e.logged_at,
        values={v.factor.key: float(v.value) for v in e.values},
        details={d.factor.key: DetailIn(note=d.note, data=d.data or {}) for d in e.details},
    )


TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _clean_details(details: dict[str, DetailIn], kind: str, factors: dict[str, Factor]) -> dict[str, DetailIn]:
    """Validate against each factor's detail_schema. Drops empty fields and empty details."""
    errors, cleaned = [], {}
    for key, d in details.items():
        f = factors.get(key)
        if f is None or f.source != "manual" or f.applies_to != kind:
            errors.append(f"{key}: no details can be added here")
            continue
        schema = {fld["key"]: fld for fld in (f.detail_schema or [])}
        data = {}
        for fk, v in d.data.items():
            fld = schema.get(fk)
            if fld is None:
                errors.append(f"{key}.{fk}: unknown field")
                continue
            if v is None or v == "" or v == []:
                continue  # cleared field
            t = fld["type"]
            if t == "number":
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not (fld["min"] <= v <= fld["max"]):
                    errors.append(f"{key}.{fk}: must be a number from {fld['min']} to {fld['max']}")
                    continue
            elif t == "choice":
                if v not in fld["options"]:
                    errors.append(f"{key}.{fk}: must be one of {', '.join(fld['options'])}")
                    continue
            elif t == "multi":
                if not isinstance(v, list) or any(x not in fld["options"] for x in v):
                    errors.append(f"{key}.{fk}: must be a list from {', '.join(fld['options'])}")
                    continue
                v = [o for o in fld["options"] if o in v]  # dedupe, keep option order
            elif t == "time":
                if not isinstance(v, str) or not TIME_RE.match(v):
                    errors.append(f"{key}.{fk}: must be a time like 23:30")
                    continue
            data[fk] = v
        note = (d.note or "").strip() or None
        if note or data:
            cleaned[key] = DetailIn(note=note, data=data)
    if errors:
        raise HTTPException(422, errors)
    return cleaned


def _validate_values(values: dict[str, float], kind: str, factors: dict[str, Factor]) -> None:
    errors = []
    for key, value in values.items():
        f = factors.get(key)
        if f is None:
            errors.append(f"{key}: unknown factor")
            continue
        if f.source != "manual":
            errors.append(f"{key}: filled in automatically from {f.source.title()}")
            continue
        if f.applies_to != kind:
            errors.append(f"{key}: belongs to the {f.applies_to} check-in")
            continue
        if f.value_type == "bool" and value not in (0, 1):
            errors.append(f"{key}: must be 0 or 1")
        if f.value_type == "scale" and value != int(value):
            errors.append(f"{key}: must be a whole number")
        if f.min_value is not None and value < f.min_value:
            errors.append(f"{key}: below minimum {f.min_value}")
        if f.max_value is not None and value > f.max_value:
            errors.append(f"{key}: above maximum {f.max_value}")
    if errors:
        raise HTTPException(422, errors)


def _load(db: Session, user_id: uuid.UUID, day: date, kind: str) -> Entry | None:
    return db.scalar(
        select(Entry)
        .options(selectinload(Entry.values).selectinload(FactorValue.factor),
                 selectinload(Entry.details).selectinload(EntryDetail.factor))
        .where(Entry.user_id == user_id, Entry.day == day, Entry.kind == kind)
    )


@router.get("", response_model=list[EntryOut])
def list_entries(
    start: date | None = Query(None, description="Defaults to 30 days before end"),
    end: date | None = Query(None, description="Defaults to your today"),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    end = end or user_today(ensure_profile(db, user_id))
    start = start or end - timedelta(days=30)
    if start > end:
        raise HTTPException(422, "start must be on or before end")
    rows = db.scalars(
        select(Entry)
        .options(selectinload(Entry.values).selectinload(FactorValue.factor),
                 selectinload(Entry.details).selectinload(EntryDetail.factor))
        .where(Entry.user_id == user_id, Entry.day.between(start, end))
        .order_by(Entry.day.desc(), Entry.kind.desc())  # morning before evening
    )
    return [_to_out(e) for e in rows]


@router.get("/{day}/{kind}", response_model=EntryOut)
def get_entry(
    day: date, kind: Kind,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    e = _load(db, user_id, day, kind)
    if e is None:
        raise HTTPException(404, "No check-in for that day")
    return _to_out(e)


@router.put("/{day}/{kind}", response_model=EntryOut)
def save_entry(
    day: date, kind: Kind, body: EntryIn,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    """Create or fully replace the check-in for a day. Any past date is allowed."""
    profile = ensure_profile(db, user_id)
    if day > user_today(profile):
        raise HTTPException(422, "Can't log a day that hasn't started yet")
    if day < EARLIEST_DAY:
        raise HTTPException(422, f"Days before {EARLIEST_DAY} aren't supported")

    factors = {f.key: f for f in available_factors(db, user_id)}
    _validate_values(body.values, kind, factors)
    details = _clean_details(body.details, kind, factors)

    # Atomic upsert: safe if the same check-in is saved twice at once.
    entry_id = db.scalar(
        insert(Entry)
        .values(user_id=user_id, day=day, kind=kind, score=body.score, note=body.note)
        .on_conflict_do_update(
            constraint="uq_entries_user_day_kind",
            set_={"score": body.score, "note": body.note, "logged_at": datetime.now().astimezone()},
        )
        .returning(Entry.id)
    )
    db.execute(delete(FactorValue).where(FactorValue.entry_id == entry_id))
    for key, value in body.values.items():
        db.add(FactorValue(entry_id=entry_id, factor_id=factors[key].id, value=value))
    db.execute(delete(EntryDetail).where(EntryDetail.entry_id == entry_id))
    for key, d in details.items():
        db.add(EntryDetail(entry_id=entry_id, factor_id=factors[key].id, note=d.note, data=d.data))
    db.commit()

    db.expire_all()
    return _to_out(_load(db, user_id, day, kind))


@router.delete("/{day}/{kind}", status_code=204)
def delete_entry(
    day: date, kind: Kind,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    result = db.execute(
        delete(Entry).where(Entry.user_id == user_id, Entry.day == day, Entry.kind == kind)
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "No check-in for that day")
    return Response(status_code=204)
