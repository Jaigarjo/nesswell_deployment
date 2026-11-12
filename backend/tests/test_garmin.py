"""Garmin integration against a fake client that mimics python-garminconnect."""
import json
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

from app import garmin
from tests.conftest import make_token

PASSWORD = "hunter2-very-secret"


class FakeInner:
    def __init__(self, owner): self.owner = owner
    def dumps(self): return json.dumps({"access_token": f"at-{self.owner.refreshes}", "refresh_token": "rt"})


class FakeGarmin:
    """Behaves like garminconnect.Garmin for the calls we use."""
    mfa_required = False
    rate_limit = False
    reject_tokens = False
    instances = []

    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.email, self.password, self.return_on_mfa = email, password, return_on_mfa
        self.refreshes = 0
        self.client = FakeInner(self)
        FakeGarmin.instances.append(self)

    def login(self, tokenstore=None):
        if tokenstore:
            if FakeGarmin.reject_tokens:
                raise GarminConnectAuthenticationError("expired")
            assert json.loads(tokenstore)["refresh_token"] == "rt"
            self.refreshes += 1  # pretend the library refreshed the access token
            return None, None
        if self.password != PASSWORD:
            raise GarminConnectAuthenticationError("bad credentials")
        if FakeGarmin.mfa_required:
            return "needs_mfa", None
        return None, None

    def resume_login(self, _state, code):
        if code != "123456":
            raise GarminConnectAuthenticationError("bad code")
        return None, None

    def get_sleep_data(self, d):
        if FakeGarmin.rate_limit:
            raise GarminConnectTooManyRequestsError("429")
        return {"dailySleepDTO": {"sleepTimeSeconds": 7.5 * 3600, "sleepScores": {"overall": {"value": 82}}}}

    def get_hrv_data(self, d):
        return {"hrvSummary": {"lastNightAvg": 48}}

    def get_stats(self, d):
        return {"restingHeartRate": 54, "averageStressLevel": -1, "totalSteps": 9120, "bodyBatteryAtWakeTime": 71}


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeGarmin.mfa_required = FakeGarmin.rate_limit = FakeGarmin.reject_tokens = False
    FakeGarmin.instances = []
    monkeypatch.setattr(garmin, "client_factory", FakeGarmin)
    garmin._pending.clear()


def user():
    from app.main import app
    c = TestClient(app)
    return c, {"Authorization": f"Bearer {make_token(uuid.uuid4())}"}


def stored_row(c, h):
    from app.db import SessionLocal
    from app.models import GarminConnection
    uid = uuid.UUID(c.get("/me", headers=h).json()["user_id"])
    with SessionLocal() as db:
        return db.get(GarminConnection, uid)


def test_connect_stores_encrypted_tokens_never_password():
    c, h = user()
    r = c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD})
    assert r.json() == {"status": "connected"}
    row = stored_row(c, h)
    assert PASSWORD not in row.tokens_enc and "access_token" not in row.tokens_enc   # encrypted
    assert json.loads(garmin.decrypt(row.tokens_enc))["refresh_token"] == "rt"
    # background backfill ran (TestClient runs background tasks) and wrote 30 days
    metrics = c.get(f"/metrics?start=2000-01-01&end=2100-01-01", headers=h).json()
    assert len(metrics) == garmin.BACKFILL_DAYS
    day = next(iter(metrics.values()))
    assert day == {"g_sleep_hours": 7.5, "g_sleep_score": 82, "g_hrv": 48, "g_resting_hr": 54,
                   "g_steps": 9120, "g_body_battery": 71}  # stress -1 = "no data", dropped
    assert c.get("/garmin", headers=h).json()["status"] == "connected"


def test_wrong_password():
    c, h = user()
    r = c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": "nope"})
    assert r.status_code == 400 and "didn't accept" in r.json()["detail"]
    assert c.get("/garmin", headers=h).json() == {"connected": False}


def test_mfa_two_step_with_retry():
    FakeGarmin.mfa_required = True
    c, h = user()
    assert c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD}).json() == {"status": "needs_mfa"}
    assert c.get("/garmin", headers=h).json() == {"connected": False}
    assert c.post("/garmin/mfa", headers=h, json={"code": "000000"}).status_code == 400
    assert c.post("/garmin/mfa", headers=h, json={"code": "123456"}).json() == {"status": "connected"}  # retry works
    assert c.post("/garmin/mfa", headers=h, json={"code": "123456"}).status_code == 410  # used up


def test_mfa_expires(monkeypatch):
    FakeGarmin.mfa_required = True
    c, h = user()
    c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD})
    monkeypatch.setattr(garmin, "MFA_TTL_SECONDS", -1)
    assert c.post("/garmin/mfa", headers=h, json={"code": "123456"}).status_code == 410


def test_expired_tokens_ask_for_reauth():
    c, h = user()
    c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD})
    FakeGarmin.reject_tokens = True
    c.post("/garmin/sync", headers=h)
    s = c.get("/garmin", headers=h).json()
    assert s["status"] == "reauth" and "sign in again" in s["last_error"]


def test_rate_limit_is_reported():
    c, h = user()
    c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD})
    FakeGarmin.rate_limit = True
    assert c.post("/garmin/sync", headers=h).status_code == 429


def test_refreshed_tokens_saved_after_sync():
    c, h = user()
    c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD})
    c.post("/garmin/sync", headers=h)
    assert json.loads(garmin.decrypt(stored_row(c, h).tokens_enc))["access_token"] == "at-1"


def test_garmin_factors_not_typed_into_checkins(client, auth_header):
    h, _ = auth_header()
    r = client.put("/entries/2026-09-01/morning", headers=h, json={"score": 6, "values": {"g_hrv": 50}})
    assert r.status_code == 422 and "automatically from Garmin" in r.text
    sources = {f["key"]: f["source"] for f in client.get("/factors", headers=h).json()}
    assert sources["g_hrv"] == "garmin" and sources["exercise"] == "manual"


def test_metrics_flow_into_stats():
    c, h = user()
    c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD})
    t = date.fromisoformat(c.get("/me", headers=h).json()["today"])
    from app.db import SessionLocal
    from app.models import DailyMetric
    uid = uuid.UUID(c.get("/me", headers=h).json()["user_id"])
    with SessionLocal() as db:  # vary HRV so there's something to compare
        for i in range(20):
            db.merge(DailyMetric(user_id=uid, day=t - timedelta(days=i), key="g_hrv", value=40 + (i % 2) * 20))
        db.commit()
    for i in range(20):
        c.put(f"/entries/{t - timedelta(days=i)}/morning", headers=h, json={"score": 5 + (i % 2) * 3})
    s = c.get(f"/stats?start={t - timedelta(days=29)}&end={t}", headers=h).json()
    hrv = next(f for f in s["measures"]["morning"]["factors"] if f["key"] == "g_hrv")
    assert hrv["enough"] and hrv["diff"] == pytest.approx(3.0)


def test_only_steps_become_recommendations():
    from app.db import SessionLocal
    from app.models import Factor
    from sqlalchemy import select
    with SessionLocal() as db:
        g = {f.key: f for f in db.scalars(select(Factor).where(Factor.source == "garmin"))}
    assert g["g_steps"].higher_is == "better" and g["g_steps"].action == "Walk {good} steps"
    assert all(f.higher_is == "neutral" for k, f in g.items() if k != "g_steps")


def test_cron_sync_and_disconnect():
    c, h = user()
    c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD})
    # Just synced, so the cron skips this user; force it due.
    from app.db import SessionLocal
    from app.models import GarminConnection
    uid = uuid.UUID(c.get("/me", headers=h).json()["user_id"])
    with SessionLocal() as db:
        db.get(GarminConnection, uid).last_sync_at = None
        db.commit()
    assert c.post("/internal/sync-garmin").status_code == 403
    r = c.post("/internal/sync-garmin", headers={"X-Cron-Secret": "test-cron-secret"}).json()
    assert r["users"] >= 1 and not r["rate_limited"]

    assert c.delete("/garmin", headers=h).status_code == 204
    assert c.get("/garmin", headers=h).json() == {"connected": False}
    assert c.get("/metrics?start=2000-01-01&end=2100-01-01", headers=h).json() != {}  # data kept by default
    c.delete("/garmin?delete_data=true", headers=h)
    assert c.get("/metrics?start=2000-01-01&end=2100-01-01", headers=h).json() == {}


def test_network_blip_is_not_reauth(monkeypatch):
    from garminconnect import GarminConnectConnectionError
    c, h = user()
    c.post("/garmin/connect", headers=h, json={"email": "j@x.com", "password": PASSWORD})
    def boom(self, tokenstore=None):
        raise GarminConnectConnectionError("timeout")
    monkeypatch.setattr(FakeGarmin, "login", boom)
    r = c.post("/garmin/sync", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "connected"
    assert "reach Garmin" in r.json()["last_error"]
