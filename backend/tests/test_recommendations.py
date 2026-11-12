"""Recommendations and experiments."""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_token
from tests.test_insights import seed_lagged


def new_user():
    from app.main import app
    c = TestClient(app)
    return c, {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}


def today_of(c, h):
    return date.fromisoformat(c.get("/me", headers=h).json()["today"])


@pytest.fixture(scope="module")
def recs():
    c, h = new_user()
    seed_lagged(c, h, 120, today_of(c, h), np.random.default_rng(3))
    return c, h, c.get("/recommendations", headers=h).json()


def by_key(rows):
    return {r["key"]: r for r in rows}


def test_suggestions_ranked_with_points_and_percent(recs):
    _, _, r = recs
    s = by_key(r["suggestions"])
    ex, alc = s["exercise"], s["alcohol"]
    assert ex["action"] == "Get some exercise" and ex["gain"] > 1 and ex["percent"] > 10
    assert alc["action"] == "Skip alcohol" and alc["lag"] == 1 and alc["target"] == "morning"
    assert alc["text"].startswith("When you skip alcohol, your next morning is")
    gains = [x["gain"] for x in r["suggestions"]]
    assert gains == sorted(gains, reverse=True)
    assert all(x["ci_low"] > 0 for x in r["suggestions"])


def test_worse_factor_phrased_on_good_side(recs):
    _, _, r = recs
    ws = by_key(r["suggestions"]).get("work_stress")
    assert ws and (ws["action"].startswith("Keep work stress below") or ws["action"].endswith("or less"))


def test_never_recommends_the_bad_direction():
    """Data where drinking lifts the same evening: still no 'drink more' advice."""
    c, h = new_user()
    t = today_of(c, h)
    rng = np.random.default_rng(9)
    for i in range(40):
        alc = int(i % 2)
        score = int(np.clip(round(5 + 2.5 * alc + rng.normal(0, 0.4)), 1, 10))
        c.put(f"/entries/{t - timedelta(days=i)}/evening", headers=h, json={"score": score, "values": {"alcohol": alc}})
    r = c.get("/recommendations", headers=h).json()
    assert "alcohol" not in by_key(r["suggestions"])


def test_experiment_lifecycle(recs):
    c, h, _ = recs
    t = today_of(c, h)
    r = c.post("/experiments", headers=h, json={"key": "exercise", "target": "evening", "lag": 0, "goal_days": 3})
    assert r.status_code == 201, r.text
    exp = r.json()
    assert exp["status"] == "active" and exp["progress"]["days_total"] == 7
    assert c.post("/experiments", headers=h, json={"key": "alcohol", "target": "morning", "lag": 1}).status_code == 409

    # Today: worked out
    c.put(f"/entries/{t}/evening", headers=h, json={"score": 8, "values": {"exercise": 1, "alcohol": 0, "work_stress": 2}})
    cur = c.get("/experiments/current", headers=h).json()["experiment"]
    assert cur["progress"]["done"] == 1 and cur["progress"]["days"][0]["status"] == "done"
    assert cur["progress"]["days"][1]["status"] == "upcoming" and cur["result"] is None

    assert c.post(f"/experiments/{exp['id']}/stop", headers=h).json()["status"] == "cancelled"
    assert c.get("/recommendations", headers=h).json()["experiment"] is None


def test_experiment_result_after_window():
    """Run an experiment in the past by moving its dates, then read the result."""
    from app.db import SessionLocal
    from app.models import Experiment

    c, h = new_user()
    t = today_of(c, h)
    seed_lagged(c, h, 60, t, np.random.default_rng(4))
    exp = c.post("/experiments", headers=h, json={"key": "exercise", "target": "evening", "lag": 0}).json()
    with SessionLocal() as db:
        e = db.get(Experiment, uuid.UUID(exp["id"]))
        e.start_day, e.end_day = t - timedelta(days=9), t - timedelta(days=3)
        db.commit()
    cur = c.get("/recommendations", headers=h).json()["experiment"]
    assert cur["status"] == "completed" and cur["result"] is not None
    assert cur["result"]["verdict"]
    assert cur["progress"]["done"] + sum(d["status"] != "done" for d in cur["progress"]["days"]) == 7
    # A new one can start now
    assert c.post("/experiments", headers=h, json={"key": "exercise", "target": "evening", "lag": 0}).status_code == 201


def test_experiment_needs_data():
    c, h = new_user()
    r = c.post("/experiments", headers=h, json={"key": "exercise", "target": "evening", "lag": 0})
    assert r.status_code == 422


def test_reminders_carry_experiment_and_tips(recs):
    from app.db import SessionLocal
    from app.reminders import send_due_reminders

    c, h, _ = recs
    c.patch("/me", headers=h, json={"timezone": "UTC", "morning_reminder": "08:00", "evening_reminder": "21:00"})
    c.post("/push/subscriptions", headers=h, json={"endpoint": f"https://push.example/{uuid.uuid4()}",
                                                   "keys": {"p256dh": "x", "auth": "y"}})
    uid = c.get("/me", headers=h).json()["user_id"]
    t = today_of(c, h)
    got = []
    sender = lambda sub, payload: got.append(payload) if str(sub.user_id) == uid else None

    # Tomorrow morning, no experiment running: a tip.
    c.delete(f"/entries/{t + timedelta(days=1)}/morning", headers=h)
    with SessionLocal() as db:
        send_due_reminders(db, datetime.combine(t + timedelta(days=1), time(8, 5), timezone.utc), sender)
    assert got and "Tip:" in got[-1]["body"]

    # Start an experiment; the next morning's reminder mentions it.
    c.post("/experiments", headers=h, json={"key": "exercise", "target": "evening", "lag": 0})
    with SessionLocal() as db:
        send_due_reminders(db, datetime.combine(t + timedelta(days=2), time(8, 5), timezone.utc), sender)
    assert "Day 3 of 7" in got[-1]["body"] and "get some exercise" in got[-1]["body"]
