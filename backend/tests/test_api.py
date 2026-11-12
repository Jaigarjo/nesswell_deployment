import time


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_me_requires_token(client):
    assert client.get("/me").status_code == 401


def test_rejects_bad_tokens(client, auth_header):
    for bad in (
        {"aud": "anon"},
        {"iss": "https://evil.example/auth/v1"},
        {"exp": int(time.time()) - 10},
    ):
        headers, _ = auth_header(**bad)
        assert client.get("/me", headers=headers).status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_profile_created_on_first_request_and_is_idempotent(client, auth_header):
    headers, uid = auth_header()
    r1 = client.get("/me", headers=headers)
    r2 = client.get("/me", headers=headers)
    assert r1.status_code == r2.status_code == 200
    body = r1.json()
    assert body["user_id"] == str(uid) and body["timezone"] == "UTC"
    assert body["morning_reminder"] is None and "today" in body


def test_update_timezone(client, auth_header):
    headers, _ = auth_header()
    assert client.patch("/me", json={"timezone": "Australia/Sydney"}, headers=headers).json()["timezone"] == "Australia/Sydney"
    assert client.get("/me", headers=headers).json()["timezone"] == "Australia/Sydney"
    assert client.patch("/me", json={"timezone": "Nowhere/Land"}, headers=headers).status_code == 422


def test_reminders_partial_update(client, auth_header):
    headers, _ = auth_header()
    r = client.patch("/me", json={"morning_reminder": "08:00"}, headers=headers).json()
    assert r["morning_reminder"] == "08:00:00" and r["evening_reminder"] is None
    r = client.patch("/me", json={"evening_reminder": "22:30"}, headers=headers).json()
    assert r["morning_reminder"] == "08:00:00"  # untouched
    r = client.patch("/me", json={"morning_reminder": None}, headers=headers).json()
    assert r["morning_reminder"] is None and r["evening_reminder"] == "22:30:00"


def test_default_factors_seeded(client, auth_header):
    headers, _ = auth_header()
    factors = client.get("/factors", headers=headers).json()
    keys = [f["key"] for f in factors if f["source"] == "manual"]
    assert keys == ["sleep_hours", "sleep_quality",  # morning first
                    "exercise", "social", "alcohol", "work_stress", "diet_quality"]
    assert not any(f["custom"] for f in factors)


def test_custom_factors_are_private(client, auth_header):
    from app.db import SessionLocal
    from app.models import Factor

    alice_h, alice = auth_header()
    bob_h, _ = auth_header()
    client.get("/me", headers=alice_h)  # creates Alice's profile
    with SessionLocal() as db:
        db.add(Factor(user_id=alice, key="caffeine", label="Coffees", value_type="number",
                      applies_to="evening", min_value=0, max_value=10))
        db.commit()

    assert "caffeine" in [f["key"] for f in client.get("/factors", headers=alice_h).json()]
    assert "caffeine" not in [f["key"] for f in client.get("/factors", headers=bob_h).json()]


def test_dev_mode_refuses_remote_database(monkeypatch):
    """Demo mode skips login, so it must never start against a remote database."""
    import importlib
    import pytest
    import app.main as main_mod  # imported under normal settings first
    from app import config
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db.abcdefgh.supabase.co:5432/postgres")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="only allowed with a database on this machine"):
            importlib.reload(main_mod)
    finally:
        monkeypatch.undo()  # restore the original environment
        config.get_settings.cache_clear()
        importlib.reload(main_mod)


def test_production_still_requires_login(client):
    assert client.get("/me").status_code == 401
