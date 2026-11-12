"""Early-days layer: streaks, milestones, progress toward insights, and general tips.

This is what makes the first weeks rewarding before the statistics have enough data.
Everything here is plain counting; nothing is inferred.
"""
import uuid
from datetime import date, timedelta

import pandas as pd
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.db import get_db
from app.insights import MIN_TRAIN, build_rows
from app.models import Factor
from app.profiles import available_factors, ensure_profile, user_today
from app.stats import MIN_GROUP, load_frames, streak
from app.tips import TIPS

LOOKBACK_DAYS = 365
MILESTONES = (1, 3, 7, 14, 30, 60, 100, 200, 365)

# How to phrase a run of good days for a yes/no factor: (doing it, avoiding it).
STREAK_TEXT = {
    "exercise": ("Worked out {n} days in a row", None),
    "social": ("Saw people {n} days in a row", None),
    "alcohol": (None, "{n} alcohol-free days in a row"),
}

router = APIRouter()


def _run(series: pd.Series, good: float, today: date) -> int:
    """Consecutive days ending today (or yesterday, if today isn't logged yet) where value == good."""
    vals = {d.date(): v for d, v in series.dropna().items()}
    d = today if today in vals else today - timedelta(days=1)
    n = 0
    while d in vals and vals[d] == good:
        n += 1
        d -= timedelta(days=1)
    return n


def behaviour_streaks(features: pd.DataFrame, factors: list[Factor], today: date) -> list[dict]:
    out = []
    for f in factors:
        if f.value_type != "bool" or f.higher_is not in ("better", "worse") or f.key not in features:
            continue
        good = 1.0 if f.higher_is == "better" else 0.0
        n = _run(features[f.key], good, today)
        if n < 2:
            continue
        do_text, avoid_text = STREAK_TEXT.get(f.key, (None, None))
        if good == 1.0:
            text = (do_text or f"{f.label}: {{n}} days in a row").format(n=n)
        else:
            text = (avoid_text or f"{{n}} days in a row without: {f.label.lower()}").format(n=n)
        out.append({"key": f.key, "days": n, "text": text})
    return sorted(out, key=lambda s: -s["days"])


def _target(f: Factor) -> str:
    return "morning" if f.applies_to == "morning" else "daily"


def unlock_progress(scores: pd.DataFrame, features: pd.DataFrame, factors: list[Factor]) -> list[dict]:
    """How close each factor is to having enough days for a comparison."""
    out = []
    for f in factors:
        if f.key not in features:
            continue
        target = _target(f)
        mood = scores[target].dropna() if target in scores else pd.Series(dtype=float)
        x = features[f.key].reindex(mood.index).dropna()
        if f.value_type == "bool":
            have = {"with": int((x == 1).sum()), "without": int((x == 0).sum())}
            enough = have["with"] >= MIN_GROUP and have["without"] >= MIN_GROUP
        else:
            have = {"days": int(len(x))}
            enough = len(x) >= 2 * MIN_GROUP and x.nunique() > 1
        out.append({"key": f.key, "label": f.label, "value_type": f.value_type,
                    "source": f.source, "have": have, "needed": MIN_GROUP, "enough": bool(enough)})
    return out


def active_tips(unlocks: list[dict], factors: list[Factor]) -> list[dict]:
    """General tips for factors this person can't yet judge from their own data."""
    enough = {u["key"] for u in unlocks if u["enough"]}
    available = {f.key for f in factors}
    return [t for t in TIPS if t["key"] in available and t["key"] not in enough]


def compute(db: Session, user_id: uuid.UUID, today: date) -> dict:
    scores, features = load_frames(db, user_id, today - timedelta(days=LOOKBACK_DAYS), today)
    factors = available_factors(db, user_id)
    days_logged = int(scores["daily"].notna().sum()) if "daily" in scores else 0

    rows = build_rows(scores, features, [f.key for f in factors if f.applies_to == "evening"])
    forecast_have = int(len(rows.dropna(subset=["target", "prev_evening"])))
    unlocks = unlock_progress(scores, features, factors)

    return {
        "days_logged": days_logged,
        "streak": streak(db, user_id, today),
        "milestone": days_logged if days_logged in MILESTONES else None,
        "behaviour_streaks": behaviour_streaks(features, factors, today),
        "unlocks": unlocks,
        "forecast": {"have": min(forecast_have, MIN_TRAIN), "needed": MIN_TRAIN},
        "tips": active_tips(unlocks, factors),
    }


@router.get("/progress")
def get_progress(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    today = user_today(ensure_profile(db, user_id))
    return compute(db, user_id, today)
