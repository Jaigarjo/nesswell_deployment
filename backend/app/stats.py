"""Stats for the dashboard.

Everything for all three measures (morning, evening, whole day) is computed in
one pass and returned together, so the frontend can switch between them instantly.

Honesty rules baked in:
- Factor comparisons need MIN_GROUP days on each side before they count.
- Differences come with a 95% CI (Welch's t), so small samples look uncertain.
- These are same-day associations, not causes. Lagged effects are Part 4.
"""
import math
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyMetric, Entry, Factor, FactorValue
from app.profiles import available_factors

MEASURES = ("morning", "evening", "daily")
MIN_GROUP = 5          # days needed on each side of a comparison
ROLLING_WINDOW = "7D"  # calendar window for the trend line
ROLLING_MIN = 3        # logged days needed inside that window
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _fmt(t: float) -> str:
    """8200 -> '8,200'; 7.5 -> '7.5'."""
    return f"{t:,.0f}" if abs(t) >= 1000 else f"{t:g}"


def _num(x, digits: int = 2):
    """JSON-safe float: NaN/inf become None."""
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, digits)


def mean_ci(values: pd.Series) -> tuple[float | None, float | None]:
    n = len(values)
    if n < 2:
        return None, None
    sd = values.std(ddof=1)
    half = st.t.ppf(0.975, n - 1) * sd / math.sqrt(n)
    m = values.mean()
    return m - half, m + half


def welch_diff(high: pd.Series, low: pd.Series) -> tuple[float, float | None, float | None]:
    """Difference in means (high - low) with a 95% Welch CI."""
    diff = high.mean() - low.mean()
    n1, n2 = len(high), len(low)
    if n1 < 2 or n2 < 2:
        return diff, None, None
    v1, v2 = high.var(ddof=1) / n1, low.var(ddof=1) / n2
    se = math.sqrt(v1 + v2)
    if se == 0:
        return diff, diff, diff
    df = (v1 + v2) ** 2 / (v1**2 / (n1 - 1) + v2**2 / (n2 - 1))
    half = st.t.ppf(0.975, df) * se
    return diff, diff - half, diff + half


# ---------- loading ----------

def load_frames(db: Session, user_id: uuid.UUID, start: date, end: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (scores, features), both indexed by day.

    scores:   columns morning, evening, daily (daily = mean of whichever were logged)
    features: one column per factor key
    """
    rows = db.execute(
        select(Entry.id, Entry.day, Entry.kind, Entry.score)
        .where(Entry.user_id == user_id, Entry.day.between(start, end))
    ).all()
    entries = pd.DataFrame(rows, columns=["id", "day", "kind", "score"])

    empty_index = pd.DatetimeIndex([], name="day")
    scores = pd.DataFrame(columns=["morning", "evening", "daily"], index=empty_index, dtype=float)
    features = pd.DataFrame(index=empty_index, dtype=float)
    if entries.empty:
        return scores, features

    entries["day"] = pd.to_datetime(entries["day"])
    entries["score"] = entries["score"].astype(float)
    scores = entries.pivot_table(index="day", columns="kind", values="score", aggfunc="first")
    scores = scores.reindex(columns=["morning", "evening"])
    scores["daily"] = scores[["morning", "evening"]].mean(axis=1, skipna=True)

    vrows = db.execute(
        select(Entry.day, Factor.key, FactorValue.value)
        .join(FactorValue, FactorValue.entry_id == Entry.id)
        .join(Factor, Factor.id == FactorValue.factor_id)
        .where(Entry.user_id == user_id, Entry.day.between(start, end))
    ).all()
    # Synced device metrics (Garmin) join as extra feature columns.
    mrows = db.execute(
        select(DailyMetric.day, DailyMetric.key, DailyMetric.value)
        .where(DailyMetric.user_id == user_id, DailyMetric.day.between(start, end))
    ).all()
    allrows = list(vrows) + list(mrows)
    if allrows:
        v = pd.DataFrame(allrows, columns=["day", "key", "value"])
        v["day"] = pd.to_datetime(v["day"])
        v["value"] = v["value"].astype(float)
        features = v.pivot_table(index="day", columns="key", values="value", aggfunc="first")
    return scores.sort_index(), features.sort_index()


# ---------- per-measure pieces ----------

def summary(s: pd.Series, prev: pd.Series) -> dict:
    out = {"n_days": int(len(s)), "mean": _num(s.mean()), "sd": _num(s.std(ddof=1)) if len(s) > 1 else None,
           "prev_mean": _num(prev.mean()) if len(prev) else None, "prev_n": int(len(prev)),
           "best": None, "worst": None}
    if len(s):
        out["best"] = {"day": s.idxmax().date().isoformat(), "value": _num(s.max())}
        out["worst"] = {"day": s.idxmin().date().isoformat(), "value": _num(s.min())}
    return out


def series(s: pd.Series) -> list[dict]:
    if s.empty:
        return []
    rolling = s.rolling(ROLLING_WINDOW, min_periods=ROLLING_MIN).mean()
    return [{"day": d.date().isoformat(), "value": _num(v), "rolling": _num(r)}
            for d, v, r in zip(s.index, s.values, rolling.values)]


def weekday(s: pd.Series) -> list[dict]:
    out = []
    for i, label in enumerate(WEEKDAYS):
        g = s[s.index.dayofweek == i]
        lo, hi = mean_ci(g)
        out.append({"weekday": i, "label": label, "n": int(len(g)),
                    "mean": _num(g.mean()) if len(g) else None,
                    "ci_low": _num(lo), "ci_high": _num(hi)})
    return out


def factor_effects(s: pd.Series, features: pd.DataFrame, factors: list[Factor]) -> list[dict]:
    out = []
    for f in factors:
        if f.key not in features.columns:
            continue
        joined = pd.concat([s.rename("mood"), features[f.key].rename("x")], axis=1, join="inner").dropna()
        if joined.empty:
            continue
        x, mood = joined["x"], joined["mood"]

        if f.value_type == "bool":
            high, low = mood[x == 1], mood[x == 0]
            high_label, low_label = "Yes", "No"
            r = None
            split = {"high": ["eq", 1.0], "low": ["eq", 0.0]}
        else:
            med = float(x.median())
            if abs(med) >= 1000:  # e.g. steps: split at 8,200 rather than 8,176
                med = round(med, -2)
            high, low = mood[x >= med], mood[x < med]
            if low.empty:  # many ties at the median: split just above it instead
                high, low = mood[x > med], mood[x <= med]
                high_label, low_label = f"More than {_fmt(med)}", f"{_fmt(med)} or less"
                split = {"high": ["gt", med], "low": ["le", med]}
            else:
                high_label, low_label = f"{_fmt(med)} or more", f"Less than {_fmt(med)}"
                split = {"high": ["ge", med], "low": ["lt", med]}
            r = _num(x.corr(mood)) if len(joined) >= MIN_GROUP and x.std() > 0 and mood.std() > 0 else None

        if high.empty or low.empty:
            continue
        diff, lo, hi = welch_diff(high, low)
        enough = len(high) >= MIN_GROUP and len(low) >= MIN_GROUP
        out.append({
            "key": f.key, "label": f.label, "value_type": f.value_type, "applies_to": f.applies_to,
            "high_label": high_label, "low_label": low_label,
            "high": {"mean": _num(high.mean()), "n": int(len(high))},
            "low": {"mean": _num(low.mean()), "n": int(len(low))},
            "diff": _num(diff), "ci_low": _num(lo), "ci_high": _num(hi),
            "r": r, "enough": enough, "split": split,
            "clear": bool(enough and lo is not None and (lo > 0 or hi < 0)),  # CI excludes zero
        })
    # Clearest, biggest differences first; not-enough-data at the bottom.
    return sorted(out, key=lambda e: (not e["enough"], not e["clear"], -abs(e["diff"] or 0)))


def streak(db: Session, user_id: uuid.UUID, today: date) -> int:
    """Consecutive days with at least one check-in, ending today (or yesterday if today is still open)."""
    days = set(db.scalars(
        select(Entry.day).where(Entry.user_id == user_id, Entry.day >= today - timedelta(days=400)).distinct()
    ))
    d = today if today in days else today - timedelta(days=1)
    n = 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


# ---------- entry point ----------

def compute(db: Session, user_id: uuid.UUID, start: date, end: date, today: date) -> dict:
    length = (end - start).days + 1
    prev_start = start - timedelta(days=length)

    scores, features = load_frames(db, user_id, prev_start, end)
    in_range = scores.index >= pd.Timestamp(start)
    cur, prev = scores[in_range], scores[~in_range]
    cur_features = features[features.index >= pd.Timestamp(start)]

    factors = available_factors(db, user_id)
    measures = {}
    for m in MEASURES:
        s = cur[m].dropna() if m in cur else pd.Series(dtype=float)
        p = prev[m].dropna() if m in prev else pd.Series(dtype=float)
        measures[m] = {
            "summary": summary(s, p),
            "series": series(s),
            "weekday": weekday(s),
            # Morning mood is logged before the day's evening factors happen.
            "factors": factor_effects(
                s, cur_features,
                [f for f in factors if m != "morning" or f.applies_to == "morning"],
            ),
        }

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat(), "days": length},
        "streak": streak(db, user_id, today),
        "min_group": MIN_GROUP,
        "measures": measures,
    }


# ---------- endpoint ----------

from fastapi import APIRouter, Depends, HTTPException, Query  # noqa: E402

from app.auth import current_user_id  # noqa: E402
from app.db import get_db  # noqa: E402
from app.profiles import ensure_profile, user_today  # noqa: E402

router = APIRouter()
EARLIEST = date(2000, 1, 1)


@router.get("/stats")
def get_stats(
    start: date | None = Query(None, description="Defaults to 29 days before end"),
    end: date | None = Query(None, description="Defaults to your today"),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    today = user_today(ensure_profile(db, user_id))
    end = min(end or today, today)
    start = max(start or end - timedelta(days=29), EARLIEST)
    if start > end:
        raise HTTPException(422, "start must be on or before end")
    return compute(db, user_id, start, end, today)
