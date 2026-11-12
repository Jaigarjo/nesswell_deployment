"""Insights tests. Synthetic data with a known next-day effect (alcohol lowers tomorrow morning)."""
import uuid
from datetime import date, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_token


def new_user():
    from app.main import app
    c = TestClient(app)
    return c, {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}


def seed_lagged(c, h, days, end, rng, signal=True, last_alcohol=None):
    """evening = 5 + 1.5*exercise - 0.4*(stress-3); next morning = 6 + 0.35*(evening-6) - 1.5*alcohol."""
    prev = None
    for i in range(days - 1, -1, -1):
        d = end - timedelta(days=i)
        if prev is not None:
            ev, alc = prev
            m = 6 + (0.35 * (ev - 6) - 1.5 * alc if signal else 0) + rng.normal(0, 0.5 if signal else 1.3)
            c.put(f"/entries/{d}/morning", headers=h, json={"score": int(np.clip(round(m), 1, 10))})
        ex = int(rng.random() < 0.5)
        alc = int(rng.random() < 0.3) if not (i == 0 and last_alcohol is not None) else last_alcohol
        stress = int(rng.integers(1, 6))
        ev = 5 + (1.5 * ex - 0.4 * (stress - 3) if signal else 0) + rng.normal(0, 0.6 if signal else 1.3)
        ev = int(np.clip(round(ev), 1, 10))
        c.put(f"/entries/{d}/evening", headers=h,
              json={"score": ev, "values": {"exercise": ex, "alcohol": alc, "work_stress": stress}})
        prev = (ev, alc)


@pytest.fixture(scope="module")
def signal_user():
    c, h = new_user()
    today = date.fromisoformat(c.get("/me", headers=h).json()["today"])
    seed_lagged(c, h, 90, today, np.random.default_rng(1), last_alcohol=1)
    return c, h, c.get("/insights", headers=h).json()


def by_key(rows):
    return {r["key"]: r for r in rows}


def test_next_day_alcohol_effect(signal_user):
    _, _, ins = signal_user
    alc = by_key(ins["next_day"]["morning"])["alcohol"]
    assert alc["clear"] and -2.2 < alc["diff"] < -0.8


def test_top_insights_are_sentences(signal_user):
    _, _, ins = signal_user
    texts = [t["text"] for t in ins["top"]]
    assert any(t.startswith("The day after you drank alcohol, your morning mood was") and "lower" in t for t in texts)
    assert any(t.startswith("On days you worked out") and "higher" in t for t in texts)
    assert len({(t["key"], t["lag"]) for t in ins["top"]}) == len(ins["top"])  # no repeats


def test_model_beats_baseline_and_forecasts(signal_user):
    _, _, ins = signal_user
    assert ins["model"]["ready"] and ins["model"]["beats_baseline"]
    assert ins["model"]["mae_model"] < ins["model"]["mae_baseline"]
    f = ins["forecast"]
    assert f["available"] and f["model_used"]
    assert f["low"] <= f["value"] <= f["high"]
    # Tonight included alcohol, so it should be pulling tomorrow down.
    alcohol = [c for c in f["contributions"] if "alcohol" in c["text"].lower()]
    assert alcohol and alcohol[0]["points"] < 0


def test_forecast_needs_evening(signal_user):
    c, h, _ = signal_user
    today = date.fromisoformat(c.get("/me", headers=h).json()["today"])
    c.delete(f"/entries/{today}/evening", headers=h)
    f = c.get("/forecast", headers=h).json()["forecast"]
    assert not f["available"] and f["reason"] == "no_evening"
    assert c.get(f"/forecast?day={today + timedelta(days=1)}", headers=h).status_code == 422


def test_not_enough_data():
    c, h = new_user()
    today = date.fromisoformat(c.get("/me", headers=h).json()["today"])
    seed_lagged(c, h, 8, today, np.random.default_rng(2))
    ins = c.get("/insights", headers=h).json()
    assert not ins["model"]["ready"] and ins["forecast"]["reason"] == "not_enough_data"
    assert ins["top"] == []


def test_pure_noise_falls_back_to_usual():
    c, h = new_user()
    today = date.fromisoformat(c.get("/me", headers=h).json()["today"])
    seed_lagged(c, h, 70, today, np.random.default_rng(5), signal=False)
    ins = c.get("/insights", headers=h).json()
    assert ins["model"]["ready"] and not ins["model"]["beats_baseline"]
    f = ins["forecast"]
    assert not f["model_used"] and f["value"] == f["usual"] and f["contributions"] == []


def test_empty_user():
    c, h = new_user()
    ins = c.get("/insights", headers=h).json()
    assert ins["n_days"] == 0 and ins["top"] == [] and not ins["forecast"]["available"]


def test_factor_directions_exposed(client, auth_header):
    h, _ = auth_header()
    f = {x["key"]: x for x in client.get("/factors", headers=h).json()}
    assert f["work_stress"]["higher_is"] == "worse" and f["work_stress"]["high_label"] == "Very stressed"
    assert f["diet_quality"]["higher_is"] == "better" and f["diet_quality"]["low_label"] == "Badly"
    assert f["alcohol"]["higher_is"] == "worse"
