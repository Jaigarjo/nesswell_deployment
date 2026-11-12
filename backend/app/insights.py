"""Insights: next-day effects, plain-English findings, and a tomorrow-morning forecast.

Two tools, two jobs:
- Comparisons (Welch, same as the dashboard) are what we SHOW. They're easy to read
  and honest about uncertainty.
- A small ridge regression is what we use to PREDICT. It weighs factors together,
  so overlapping ones (drinking and seeing people often go together) don't
  double-count.

The forecast is scored walk-forward: for each past day, fit only on the days
before it, predict, and compare against the naive guess "your average so far".
If the model can't beat that, we say so and fall back to your average.
"""
import math
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.db import get_db
from app.models import Factor
from app.profiles import available_factors, ensure_profile, user_today
from app.stats import MEASURES, _num, factor_effects, load_frames

HISTORY_DAYS = 365
MIN_TRAIN = 21            # rows needed before we forecast at all
ALPHAS = (0.3, 1, 3, 10, 30)
MIN_COVERAGE = 0.6        # a factor must be logged on this share of rows to be a feature
MIN_IMPROVEMENT = 0.10    # must beat "your average" by 10%+; noise alone gets 0-3%
TOP_INSIGHTS = 6
TARGET_WORDS = {"morning": "morning mood", "evening": "evening mood", "daily": "overall mood"}

router = APIRouter()


# ---------- next-day comparisons ----------

def lag_features(features: pd.DataFrame) -> pd.DataFrame:
    """Yesterday's factor values, indexed by today."""
    lagged = features.copy()
    lagged.index = lagged.index + pd.Timedelta(days=1)
    return lagged


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


def sentence(effect: dict, target: str, lag: int) -> str:
    """Plain-English version of one clear comparison."""
    label = effect["label"]
    if effect["value_type"] == "bool":
        cond = f"you {_lower_first(label)}"
    else:
        cond = f"{_lower_first(label)} was {_lower_first(effect['high_label'])}"
    when = f"The day after {cond}" if lag else f"On days {cond}"
    direction = "higher" if effect["diff"] > 0 else "lower"
    return (f"{when}, your {TARGET_WORDS[target]} was {abs(effect['diff']):.1f} points {direction} "
            f"({effect['high']['mean']:.1f} vs {effect['low']['mean']:.1f}).")


def top_insights(same_day: dict, next_day: dict) -> list[dict]:
    cards = []
    for lag, groups in ((0, same_day), (1, next_day)):
        for target, effects in groups.items():
            for e in effects:
                if e["clear"]:
                    cards.append({
                        "text": sentence(e, target, lag), "key": e["key"], "target": target, "lag": lag,
                        "diff": e["diff"], "n_high": e["high"]["n"], "n_low": e["low"]["n"],
                    })
    # Strongest first; keep one card per factor+lag so "overall mood" doesn't just repeat evening.
    cards.sort(key=lambda c: -abs(c["diff"]))
    seen, out = set(), []
    for c in cards:
        if (c["key"], c["lag"]) in seen:
            continue
        seen.add((c["key"], c["lag"]))
        out.append(c)
    return out[:TOP_INSIGHTS]


# ---------- forecast model ----------

def build_rows(scores: pd.DataFrame, features: pd.DataFrame, evening_keys: list[str]) -> pd.DataFrame:
    """One row per day d: tomorrow-morning target plus what was known the evening before.

    Columns: target (morning of d), prev_evening (evening score of d-1),
    f:<key> (evening factors of d-1), weekend (d is Sat/Sun).
    """
    prev = pd.DataFrame(index=scores.index + pd.Timedelta(days=1))
    prev["prev_evening"] = scores["evening"].values
    for k in evening_keys:
        prev[f"f:{k}"] = features[k].reindex(scores.index).values if k in features else np.nan
    rows = prev.join(scores["morning"].rename("target"), how="left")
    rows["weekend"] = (rows.index.dayofweek >= 5).astype(float)
    return rows


def ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float):
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    y_mean = y.mean()
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - y_mean))
    return {"mu": mu, "sd": sd, "beta": beta, "y_mean": y_mean}


def ridge_predict(model, X: np.ndarray) -> np.ndarray:
    return model["y_mean"] + ((X - model["mu"]) / model["sd"]) @ model["beta"]


def walk_forward(X: np.ndarray, y: np.ndarray, alpha: float, start: int):
    """Predict each row from only the rows before it. Returns (model errors, baseline errors)."""
    errs, base = [], []
    for i in range(start, len(y)):
        m = ridge_fit(X[:i], y[:i], alpha)
        errs.append(abs(ridge_predict(m, X[i:i + 1])[0] - y[i]))
        base.append(abs(y[:i].mean() - y[i]))
    return np.array(errs), np.array(base)


def train(scores: pd.DataFrame, features: pd.DataFrame, factors: list[Factor]):
    """Returns (model_info, fitted_state) or (reason, None) when there isn't enough data."""
    evening_keys = [f.key for f in factors if f.applies_to == "evening"]
    rows = build_rows(scores, features, evening_keys)
    train_rows = rows.dropna(subset=["target", "prev_evening"])
    if len(train_rows) < MIN_TRAIN:
        return {"ready": False, "n_train": int(len(train_rows)), "needed": MIN_TRAIN}, None

    cols = ["prev_evening", "weekend"] + [
        c for c in train_rows.columns
        if c.startswith("f:") and train_rows[c].notna().mean() >= MIN_COVERAGE and train_rows[c].std() > 0
    ]
    fill = train_rows[cols].mean()
    X = train_rows[cols].fillna(fill).to_numpy(float)
    y = train_rows["target"].to_numpy(float)

    start = max(10, len(y) // 3)
    best = None
    for a in ALPHAS:
        errs, base = walk_forward(X, y, a, start)
        if best is None or errs.mean() < best[1].mean():
            best = (a, errs, base)
    alpha, errs, base = best
    model = ridge_fit(X, y, alpha)
    resid_sd = float(np.sqrt(np.mean(errs ** 2)))  # out-of-sample RMSE

    info = {
        "ready": True, "n_train": int(len(y)), "alpha": alpha,
        "mae_model": _num(errs.mean()), "mae_baseline": _num(base.mean()),
        "beats_baseline": bool(errs.mean() < (1 - MIN_IMPROVEMENT) * base.mean()),
        "features": [{"name": c, "weight": _num(b, 3)} for c, b in zip(cols, model["beta"])],
    }
    state = {"model": model, "cols": cols, "fill": fill, "resid_sd": resid_sd, "y": y}
    return info, state


def _feature_text(col: str, value: float, factors: dict[str, Factor]) -> str:
    if col == "prev_evening":
        return f"Tonight's score of {value:g}"
    if col == "weekend":
        return "Tomorrow is a weekend day" if value else "Tomorrow is a weekday"
    f = factors.get(col[2:])
    if f is None:
        return col
    if f.value_type == "bool":
        return f"{f.label}: {'yes' if value else 'no'}"
    return f"{f.label}: {value:g}"


def forecast(state, info, scores, features, factors: list[Factor], evening_day: date) -> dict:
    """Forecast the morning after `evening_day`."""
    evening_score = scores["evening"].get(pd.Timestamp(evening_day))
    if evening_score is None or pd.isna(evening_score):
        return {"available": False, "reason": "no_evening", "for_day": (evening_day + timedelta(days=1)).isoformat()}
    if state is None:
        return {"available": False, "reason": "not_enough_data", "for_day": (evening_day + timedelta(days=1)).isoformat(),
                "n_train": info["n_train"], "needed": info["needed"]}

    evening_keys = [f.key for f in factors if f.applies_to == "evening"]
    rows = build_rows(scores, features, evening_keys)
    target_ts = pd.Timestamp(evening_day + timedelta(days=1))
    row = rows.reindex([target_ts])
    if "weekend" in row:
        row["weekend"] = float(target_ts.dayofweek >= 5)
    x_raw = row.reindex(columns=state["cols"]).iloc[0]
    x = x_raw.fillna(state["fill"]).to_numpy(float)

    model, beats = state["model"], info["beats_baseline"]
    usual = float(np.mean(state["y"]))
    pred = float(ridge_predict(model, x[None, :])[0]) if beats else usual
    pred = min(10.0, max(1.0, pred))
    half = 1.28 * state["resid_sd"]  # ~80% range

    by_key = {f.key: f for f in factors}
    contributions = []
    if beats:
        z = (x - model["mu"]) / model["sd"]
        for col, c, val, missing in zip(state["cols"], z * model["beta"], x, x_raw.isna()):
            if missing or abs(c) < 0.05:
                continue
            contributions.append({"text": _feature_text(col, val, by_key), "points": _num(c)})
        contributions.sort(key=lambda d: -abs(d["points"]))

    return {
        "available": True, "for_day": target_ts.date().isoformat(),
        "value": _num(pred, 1), "low": _num(max(1.0, pred - half), 1), "high": _num(min(10.0, pred + half), 1),
        "usual": _num(usual, 1), "model_used": beats, "contributions": contributions[:4],
    }


# ---------- endpoints ----------

def _prepare(db: Session, user_id: uuid.UUID):
    today = user_today(ensure_profile(db, user_id))
    scores, features = load_frames(db, user_id, today - timedelta(days=HISTORY_DAYS), today)
    return today, scores, features, available_factors(db, user_id)


@router.get("/insights")
def get_insights(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    today, scores, features, factors = _prepare(db, user_id)
    lagged = lag_features(features)

    same_day, next_day = {}, {}
    for m in MEASURES:
        s = scores[m].dropna()
        same_day[m] = factor_effects(s, features, [f for f in factors if m != "morning" or f.applies_to == "morning"])
        next_day[m] = factor_effects(s, lagged, factors)

    info, state = train(scores, features, factors)
    return {
        "n_days": int(scores["daily"].notna().sum()) if "daily" in scores else 0,
        "top": top_insights(same_day, next_day),
        "next_day": next_day,
        "model": info,
        "forecast": forecast(state, info, scores, features, factors, today),
    }


@router.get("/forecast")
def get_forecast(
    day: date | None = Query(None, description="The evening to forecast from; defaults to today"),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    today, scores, features, factors = _prepare(db, user_id)
    day = day or today
    if day > today:
        raise HTTPException(422, "That evening hasn't happened yet")
    info, state = train(scores, features, factors)
    return {"model": info, "forecast": forecast(state, info, scores, features, factors, day)}
