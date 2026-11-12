import base64
import os
from datetime import date, datetime, time, timezone
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.days import reminder_due


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


# ---------- timing ----------

def test_due_at_and_after_reminder_time():
    # Sydney 08:00 AEST = 22:00 UTC previous day
    assert reminder_due(utc(2026, 6, 4, 22, 0), "Australia/Sydney", time(8)) == date(2026, 6, 5)
    assert reminder_due(utc(2026, 6, 4, 23, 30), "Australia/Sydney", time(8)) == date(2026, 6, 5)


def test_not_due_before_or_long_after():
    assert reminder_due(utc(2026, 6, 4, 21, 45), "Australia/Sydney", time(8)) is None  # 07:45
    assert reminder_due(utc(2026, 6, 5, 2, 0), "Australia/Sydney", time(8)) is None    # 12:00, window passed


def test_after_midnight_evening_reminder_belongs_to_previous_day():
    # Madrid 00:30 CEST on the 6th = 22:30 UTC on the 5th -> logical day the 5th
    assert reminder_due(utc(2026, 7, 5, 22, 35), "Europe/Madrid", time(0, 30)) == date(2026, 7, 5)


# ---------- sending ----------

def _setup_user(client, auth_header, tz, morning=None, evening=None):
    h, uid = auth_header()
    body = {"timezone": tz}
    if morning: body["morning_reminder"] = morning
    if evening: body["evening_reminder"] = evening
    client.patch("/me", json=body, headers=h)
    client.post("/push/subscriptions", headers=h, json={
        "endpoint": f"https://push.example/{uid}", "keys": {"p256dh": "x", "auth": "y"}})
    return h, uid


def test_sends_once_and_skips_if_logged(client, auth_header):
    from app.db import SessionLocal
    from app.reminders import send_due_reminders

    h, uid = _setup_user(client, auth_header, "Australia/Sydney", morning="08:00", evening="21:00")
    calls = []
    sender = lambda sub, payload: calls.append((sub.user_id, payload["title"]))

    at_8am = utc(2026, 6, 4, 22, 5)
    with SessionLocal() as db:
        send_due_reminders(db, at_8am, sender)
        send_due_reminders(db, at_8am, sender)  # second cron run: no duplicate
    assert calls.count((uid, "Morning check-in")) == 1

    client.put("/entries/2026-06-05/evening", json={"score": 7}, headers=h)
    with SessionLocal() as db:
        stats = send_due_reminders(db, utc(2026, 6, 5, 11, 5), sender)  # 21:05 Sydney
    assert (uid, "Evening check-in") not in calls
    assert stats["skipped_logged"] >= 1


def test_dead_subscription_removed(client, auth_header):
    from app.db import SessionLocal
    from app.models import PushSubscription
    from app.reminders import Gone, send_due_reminders
    from sqlalchemy import select

    _, uid = _setup_user(client, auth_header, "Europe/Madrid", morning="07:00")

    def sender(sub, payload):
        if sub.user_id == uid:
            raise Gone()

    with SessionLocal() as db:
        send_due_reminders(db, utc(2026, 7, 1, 5, 10), sender)  # 07:10 Madrid
        assert db.scalars(select(PushSubscription).where(PushSubscription.user_id == uid)).all() == []


def test_cron_endpoint_requires_secret(client):
    assert client.post("/internal/send-reminders").status_code in (403, 503)


def test_real_webpush_encryption(monkeypatch):
    """Runs pywebpush's real encryption + VAPID signing with our key format; only the HTTP call is faked."""
    import subprocess, sys
    from app.config import get_settings
    from app.models import PushSubscription
    from app.reminders import send_push

    out = subprocess.check_output([sys.executable, "scripts/gen_vapid.py"], text=True)
    keys = dict(line.split("=", 1) for line in out.strip().splitlines())
    monkeypatch.setenv("VAPID_PUBLIC_KEY", keys["VAPID_PUBLIC_KEY"])
    monkeypatch.setenv("VAPID_PRIVATE_KEY", keys["VAPID_PRIVATE_KEY"])
    get_settings.cache_clear()

    # A browser-style subscription
    browser = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    sub = PushSubscription(endpoint="https://fcm.googleapis.com/fcm/send/abc",
                           p256dh=b64(browser), auth=b64(os.urandom(16)))

    fake = MagicMock(status_code=201)
    with patch("pywebpush.requests.post", return_value=fake) as post:
        send_push(sub, {"title": "t", "body": "b"})
    headers = post.call_args.kwargs["headers"]
    assert headers["authorization"].startswith("vapid t=")
    assert headers["content-encoding"] == "aes128gcm"
    get_settings.cache_clear()
