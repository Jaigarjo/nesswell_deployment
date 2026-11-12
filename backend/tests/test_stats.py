"""Stats tests on synthetic data with known effects baked in."""
from datetime import date, timedelta

import numpy as np
import pytest

from app.stats import mean_ci, welch_diff


def seed(client, headers, days=60, end=date(2026, 8, 31), seed=0):
    """Evening mood = 5 + 2 if worked out; morning mood = 3 + 0.5 * sleep_hours; Saturdays +1."""
    rng = np.random.default_rng(seed)
    for i in range(days):
        d = end - timedelta(days=i)
        sleep = float(rng.choice([5, 6, 6.5, 7, 7.5, 8, 9]))
        morning = round(3 + 0.5 * sleep + rng.normal(0, 0.5))
        exercise = int(rng.random() < 0.5)
        evening = 5 + 2 * exercise + (1 if d.weekday() == 5 else 0) + round(rng.normal(0, 0.5))
        client.put(f"/entries/{d}/morning", headers=headers,
                   json={"score": int(np.clip(morning, 1, 10)), "values": {"sleep_hours": sleep}})
        if i % 7 != 3:  # skip some evenings so daily != evening
            client.put(f"/entries/{d}/evening", headers=headers,
                       json={"score": int(np.clip(evening, 1, 10)), "values": {"exercise": exercise, "alcohol": 0}})


@pytest.fixture(scope="module")
def seeded(request):
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.conftest import make_token
    import uuid
    client = TestClient(app)
    uid = uuid.uuid4()
    headers = {"Authorization": f"Bearer {make_token(uid)}"}
    seed(client, headers)
    stats = client.get("/stats?start=2026-07-03&end=2026-08-31", headers=headers).json()
    return client, headers, stats


def by_key(rows):
    return {r["key"]: r for r in rows}


def test_shape_and_all_measures(seeded):
    _, _, s = seeded
    assert set(s["measures"]) == {"morning", "evening", "daily"}
    assert s["range"]["days"] == 60
    m = s["measures"]["morning"]
    assert m["summary"]["n_days"] == 60
    assert len(m["weekday"]) == 7 and len(m["series"]) == 60
    assert s["measures"]["evening"]["summary"]["n_days"] < 60  # skipped evenings


def test_exercise_effect_recovered(seeded):
    _, _, s = seeded
    ex = by_key(s["measures"]["evening"]["factors"])["exercise"]
    assert ex["enough"] and ex["clear"]
    assert 1.5 < ex["diff"] < 2.5
    assert ex["ci_low"] > 0


def test_sleep_split_and_correlation(seeded):
    _, _, s = seeded
    sl = by_key(s["measures"]["morning"]["factors"])["sleep_hours"]
    assert sl["diff"] > 0 and sl["r"] > 0.5
    assert "or more" in sl["high_label"] or "More than" in sl["high_label"]


def test_constant_factor_dropped(seeded):
    _, _, s = seeded
    assert "alcohol" not in by_key(s["measures"]["evening"]["factors"])  # always 0: nothing to compare


def test_daily_is_mean_of_logged(seeded):
    _, _, s = seeded
    m = {p["day"]: p["value"] for p in s["measures"]["morning"]["series"]}
    e = {p["day"]: p["value"] for p in s["measures"]["evening"]["series"]}
    for p in s["measures"]["daily"]["series"]:
        parts = [x for x in (m.get(p["day"]), e.get(p["day"])) if x is not None]
        assert p["value"] == pytest.approx(sum(parts) / len(parts), abs=0.01)


def test_rolling_needs_enough_points(seeded):
    _, _, s = seeded
    first = s["measures"]["morning"]["series"][:2]
    assert all(p["rolling"] is None for p in first)
    assert s["measures"]["morning"]["series"][10]["rolling"] is not None


def test_previous_period(seeded):
    client, headers, _ = seeded
    s = client.get("/stats?start=2026-08-02&end=2026-08-31", headers=headers).json()
    assert s["measures"]["morning"]["summary"]["prev_n"] == 30


def test_small_sample_not_enough():
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.conftest import make_token
    import uuid
    client = TestClient(app)
    h = {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    for i, ex in enumerate([1, 0, 1, 0, 1, 0]):
        client.put(f"/entries/2026-08-{10+i:02d}/evening", headers=h, json={"score": 5 + ex * 3, "values": {"exercise": ex}})
    s = client.get("/stats?start=2026-08-01&end=2026-08-31", headers=h).json()
    ex = by_key(s["measures"]["evening"]["factors"])["exercise"]
    assert not ex["enough"] and not ex["clear"]


def test_empty_user_and_isolation(client, auth_header):
    h, _ = auth_header()
    s = client.get("/stats", headers=h).json()
    for m in s["measures"].values():
        assert m["summary"]["n_days"] == 0 and m["series"] == [] and m["factors"] == []
    assert s["streak"] == 0


def test_streak(client, auth_header):
    h, _ = auth_header()
    today = date.fromisoformat(client.get("/me", headers=h).json()["today"])
    for i in (1, 2, 3, 5):
        client.put(f"/entries/{today - timedelta(days=i)}/morning", headers=h, json={"score": 5})
    assert client.get("/stats", headers=h).json()["streak"] == 3  # today still open, counts from yesterday


def test_stat_helpers():
    import pandas as pd
    lo, hi = mean_ci(pd.Series([5, 6, 7, 6, 5.0]))
    assert lo < 5.8 < hi
    d, lo, hi = welch_diff(pd.Series([8, 8, 8.0]), pd.Series([5, 5, 5.0]))
    assert d == 3 and lo == hi == 3


def test_morning_ignores_evening_factors(seeded):
    _, _, s = seeded
    assert "exercise" not in by_key(s["measures"]["morning"]["factors"])
    assert "sleep_hours" in by_key(s["measures"]["evening"]["factors"])
