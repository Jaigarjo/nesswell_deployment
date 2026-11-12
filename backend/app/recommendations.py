"""Recommendations: what helps you most, and week-long experiments to test it.

Rules:
- Only factors with a direction (higher is better/worse) can be recommended, and
  only in the good direction. A pattern that points the "wrong" way (say, alcohol
  lifting your evening) is never turned into advice.
- A suggestion needs a clear comparison (CI excludes zero, 5+ days each side).
- Effects are shown in points on the 1-10 scale, with percent vs the other days as context.
"""
import uuid
from datetime import date, timedelta
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.db import get_db
from app.insights import lag_features
from app.models import Experiment, Factor, Profile
from app.profiles import available_factors, ensure_profile, user_today
from app.stats import _fmt, _num, factor_effects, load_frames, welch_diff

HISTORY_DAYS = 365
EXPERIMENT_DAYS = 7
PRIOR_DAYS = 28
SHOW_FINISHED_FOR = timedelta(days=14)

OPS = {
    "eq": lambda x, t: x == t, "ge": lambda x, t: x >= t, "gt": lambda x, t: x > t,
    "lt": lambda x, t: x < t, "le": lambda x, t: x <= t,
}
TARGET_WORDS = {
    (0, "morning"): "your morning mood", (0, "evening"): "your evening mood",
    (0, "daily"): "your day overall", (1, "morning"): "your next morning",
}

router = APIRouter()


# ---------- wording ----------

def good_phrase(op: str, t: float) -> str:
    n = _fmt(t)
    return {"ge": f"{n}+", "gt": f"more than {n}", "lt": f"below {n}", "le": f"{n} or less"}.get(op, "")


def action_text(f: Factor, op: str, t: float) -> str:
    good = good_phrase(op, t)
    if f.action:
        return f.action.replace("{good}", good).strip()
    if f.value_type == "bool":
        return f.label if op == "eq" and t == 1 else f"Avoid: {f.label[:1].lower()}{f.label[1:]}"
    return f"Keep {f.label.lower()} {good}"


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


def suggestion_sentence(action: str, lag: int, target: str, gain: float, pct: float | None) -> str:
    pct_txt = f" ({pct:+.0f}%)" if pct is not None else ""
    return (f"When you {_lower_first(action)}, {TARGET_WORDS[(lag, target)]} is "
            f"{gain:.1f} points higher{pct_txt} than when you don't.")


# ---------- suggestions ----------

def _candidates(f: Factor, scores: pd.DataFrame, features: pd.DataFrame, lagged: pd.DataFrame):
    """(lag, target, effect) for every comparison that makes sense for this factor."""
    combos = [(0, "evening"), (0, "daily"), (1, "morning")]
    if f.applies_to == "morning":
        combos.insert(0, (0, "morning"))
    for lag, target in combos:
        s = scores[target].dropna() if target in scores else pd.Series(dtype=float)
        rows = factor_effects(s, lagged if lag else features, [f])
        if rows:
            yield lag, target, rows[0]


def _as_suggestion(f: Factor, lag: int, target: str, e: dict) -> dict:
    good_side = "high" if f.higher_is == "better" else "low"
    bad_side = "low" if good_side == "high" else "high"
    good, bad = e[good_side], e[bad_side]
    gain = good["mean"] - bad["mean"]
    op, t = e["split"][good_side]
    action = action_text(f, op, t)
    pct = gain / bad["mean"] * 100 if bad["mean"] else None
    # CI of the gain: flip the high-minus-low interval when "good" is the low side.
    lo, hi = e["ci_low"], e["ci_high"]
    if good_side == "low" and lo is not None:
        lo, hi = -hi, -lo
    return {
        "key": f.key, "label": f.label, "action": action, "target": target, "lag": lag,
        "gain": _num(gain), "percent": _num(pct, 0), "ci_low": _num(lo), "ci_high": _num(hi),
        "good_mean": good["mean"], "bad_mean": bad["mean"], "n_good": good["n"], "n_bad": bad["n"],
        "clear": bool(e["clear"] and gain > 0), "rule": [op, t],
        "text": suggestion_sentence(action, lag, target, gain, pct),
    }


def all_candidates(db: Session, user_id: uuid.UUID, today: date) -> list[dict]:
    scores, features = load_frames(db, user_id, today - timedelta(days=HISTORY_DAYS), today)
    lagged = lag_features(features)
    out = []
    for f in available_factors(db, user_id):
        if f.higher_is not in ("better", "worse"):
            continue
        for lag, target, e in _candidates(f, scores, features, lagged):
            out.append(_as_suggestion(f, lag, target, e))
    return out


def suggestions(db: Session, user_id: uuid.UUID, today: date) -> list[dict]:
    """Best clear, direction-consistent effect per factor, biggest first."""
    best: dict[str, dict] = {}
    for c in all_candidates(db, user_id, today):
        if c["clear"] and (c["key"] not in best or c["gain"] > best[c["key"]]["gain"]):
            best[c["key"]] = c
    return sorted(best.values(), key=lambda s: -s["gain"])


# ---------- experiments ----------

def _active(db: Session, user_id: uuid.UUID) -> Experiment | None:
    return db.scalar(select(Experiment).where(Experiment.user_id == user_id, Experiment.status == "active"))


def evaluate(db: Session, exp: Experiment, today: date) -> dict:
    """Progress so far, and a result once the window has ended. Marks finished experiments completed."""
    lo_day = exp.start_day - timedelta(days=PRIOR_DAYS)
    scores, features = load_frames(db, exp.user_id, lo_day, exp.end_day + timedelta(days=1))
    key, op, t = exp.factor.key, exp.op, float(exp.threshold)
    col = features[key] if key in features else pd.Series(dtype=float)
    mood = scores[exp.target] if exp.target in scores else pd.Series(dtype=float)

    days, done, with_mood, without_mood = [], 0, [], []
    d = exp.start_day
    while d <= exp.end_day:
        ts = pd.Timestamp(d)
        if d > today:
            status = "upcoming"
        elif ts in col.index and not pd.isna(col[ts]):
            status = "done" if OPS[op](float(col[ts]), t) else "missed"
        elif d == today:
            status = "today"  # still time to do it
        else:
            status = "unlogged"
        if status == "done":
            done += 1
        out_ts = pd.Timestamp(d + timedelta(days=exp.lag))
        m = mood.get(out_ts)
        if m is not None and not pd.isna(m) and status in ("done", "missed"):
            (with_mood if status == "done" else without_mood).append(float(m))
        days.append({"day": d.isoformat(), "status": status})
        d += timedelta(days=1)

    finished = today > exp.end_day
    if finished and exp.status == "active":
        exp.status = "completed"
        db.commit()

    result = None
    if finished:
        window = mood[(mood.index >= pd.Timestamp(exp.start_day)) & (mood.index <= pd.Timestamp(exp.end_day + timedelta(days=exp.lag)))].dropna()
        prior = mood[(mood.index >= pd.Timestamp(lo_day)) & (mood.index < pd.Timestamp(exp.start_day))].dropna()
        diff = lo = hi = None
        if len(with_mood) >= 2 and len(without_mood) >= 2:
            diff, lo, hi = welch_diff(pd.Series(with_mood), pd.Series(without_mood))
        vs_prior = float(window.mean() - prior.mean()) if len(window) and len(prior) else None

        if done < exp.goal_days:
            verdict = f"You managed {done} of {exp.goal_days} days, so there's not enough to judge. Worth another try."
        elif diff is not None and lo is not None and lo > 0:
            verdict = "It helped: your mood was clearly higher on the days you did it."
        elif (diff is not None and diff > 0) or (diff is None and vs_prior is not None and vs_prior > 0):
            verdict = "Leaning helpful, but one week is too short to be sure. Repeat it to confirm."
        else:
            verdict = "No sign it helped this week. One week is short, so this isn't the final word."
        result = {
            "with_mean": _num(sum(with_mood) / len(with_mood)) if with_mood else None,
            "without_mean": _num(sum(without_mood) / len(without_mood)) if without_mood else None,
            "n_with": len(with_mood), "n_without": len(without_mood),
            "diff": _num(diff), "ci_low": _num(lo), "ci_high": _num(hi),
            "window_mean": _num(window.mean()) if len(window) else None,
            "prior_mean": _num(prior.mean()) if len(prior) else None,
            "vs_prior": _num(vs_prior), "verdict": verdict,
        }

    day_index = min((today - exp.start_day).days + 1, (exp.end_day - exp.start_day).days + 1)
    return {
        "id": str(exp.id), "key": key, "label": exp.factor.label, "applies_to": exp.factor.applies_to,
        "action": exp.action, "target": exp.target, "lag": exp.lag,
        "start_day": exp.start_day.isoformat(), "end_day": exp.end_day.isoformat(),
        "goal_days": exp.goal_days, "status": exp.status,
        "progress": {"day": max(day_index, 1), "days_total": len(days), "done": done, "days": days},
        "result": result,
    }


def current_experiment(db: Session, user_id: uuid.UUID, today: date) -> dict | None:
    """The running experiment, or one that finished in the last two weeks."""
    exp = _active(db, user_id) or db.scalar(
        select(Experiment)
        .where(Experiment.user_id == user_id, Experiment.status == "completed",
               Experiment.end_day >= today - SHOW_FINISHED_FOR)
        .order_by(Experiment.end_day.desc())
    )
    return evaluate(db, exp, today) if exp else None


# ---------- reminder wording ----------

def reminder_message(db: Session, p: Profile, kind: str, day: date, default: dict) -> dict:
    """Personalise a reminder with the running experiment or a rotating top tip."""
    exp = _active(db, p.user_id)
    if exp and day > exp.end_day:
        evaluate(db, exp, day)  # marks it completed
        exp = None
    finished = db.scalar(
        select(Experiment).where(Experiment.user_id == p.user_id, Experiment.status == "completed",
                                 Experiment.finished_notified.is_(False))
    )
    if kind == "morning" and finished:
        finished.finished_notified = True
        db.commit()
        return {"title": "Your experiment finished", "body": f"See how \"{finished.action}\" went."}

    if exp:
        i = (day - exp.start_day).days + 1
        n = (exp.end_day - exp.start_day).days + 1
        if kind == "morning":
            return {"title": default["title"], "body": f"Day {i} of {n}: {_lower_first(exp.action)} today. How did you sleep?"}
        if exp.factor.applies_to == "evening":
            return {"title": default["title"], "body": f"How was today? Log whether you managed to {_lower_first(exp.action)}."}
        return default

    if kind == "morning":
        top = suggestions(db, p.user_id, day)[:3]
        if top:
            s = top[day.toordinal() % len(top)]
            return {"title": default["title"],
                    "body": f"{default['body']} Tip: {_lower_first(s['action'])}. It tends to lift {TARGET_WORDS[(s['lag'], s['target'])]} by {s['gain']:.1f} points."}
        # No personal patterns yet: rotate the general, research-based tips.
        from app.progress import compute as progress
        tips = progress(db, p.user_id, day)["tips"]
        if tips:
            t = tips[day.toordinal() % len(tips)]
            return {"title": default["title"], "body": f"{default['body']} {t['short']}"}
    return default


# ---------- endpoints ----------

class ExperimentIn(BaseModel):
    key: str
    target: Literal["morning", "evening", "daily"]
    lag: int = Field(ge=0, le=1)
    goal_days: int = Field(default=4, ge=1, le=EXPERIMENT_DAYS)


@router.get("/recommendations")
def get_recommendations(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    today = user_today(ensure_profile(db, user_id))
    return {"suggestions": suggestions(db, user_id, today), "experiment": current_experiment(db, user_id, today)}


@router.get("/experiments/current")
def get_current_experiment(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    """Just the running (or recently finished) experiment; cheap enough for every check-in."""
    today = user_today(ensure_profile(db, user_id))
    return {"experiment": current_experiment(db, user_id, today)}


@router.post("/experiments", status_code=201)
def start_experiment(body: ExperimentIn, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    today = user_today(ensure_profile(db, user_id))
    if _active(db, user_id):
        raise HTTPException(409, "You already have an experiment running. Finish or stop it first.")
    match = next((c for c in all_candidates(db, user_id, today)
                  if c["key"] == body.key and c["target"] == body.target and c["lag"] == body.lag), None)
    if match is None:
        raise HTTPException(422, "Not enough data on this factor to set up an experiment yet.")
    factor = next(f for f in available_factors(db, user_id) if f.key == body.key)
    op, t = match["rule"]
    exp = Experiment(
        user_id=user_id, factor_id=factor.id, target=body.target, lag=body.lag, op=op, threshold=t,
        action=match["action"], start_day=today, end_day=today + timedelta(days=EXPERIMENT_DAYS - 1),
        goal_days=body.goal_days,
    )
    db.add(exp)
    try:
        db.commit()
    except IntegrityError:  # a second tap raced the first
        db.rollback()
        raise HTTPException(409, "You already have an experiment running.")
    db.refresh(exp)
    return evaluate(db, exp, today)


@router.post("/experiments/{exp_id}/stop")
def stop_experiment(exp_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    exp = db.scalar(select(Experiment).where(Experiment.id == exp_id, Experiment.user_id == user_id))
    if exp is None:
        raise HTTPException(404, "Experiment not found")
    if exp.status == "active":
        exp.status = "cancelled"
        db.commit()
    return {"status": exp.status}


@router.get("/experiments")
def list_experiments(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    today = user_today(ensure_profile(db, user_id))
    rows = db.scalars(select(Experiment).where(Experiment.user_id == user_id)
                      .order_by(Experiment.created_at.desc())).all()
    return [evaluate(db, e, today) for e in rows if e.status != "cancelled"]
