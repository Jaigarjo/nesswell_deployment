"""Early-days layer: streaks, milestones, unlock progress, general tips."""
import uuid
from datetime import date, datetime, time, timedelta, timezone


def today_of(c, h):
    return date.fromisoformat(c.get("/me", headers=h).json()["today"])


def evening(c, h, d, score=6, **values):
    vals = {"exercise": 0, "social": 0, "alcohol": 0, **values}
    assert c.put(f"/entries/{d}/evening", headers=h, json={"score": score, "values": vals}).status_code == 200


def test_new_user_gets_all_tips_and_nothing_else(client, auth_header):
    h, _ = auth_header()
    p = client.get("/progress", headers=h).json()
    assert p["days_logged"] == 0 and p["streak"] == 0 and p["milestone"] is None
    assert p["behaviour_streaks"] == []
    keys = {t["key"] for t in p["tips"]}
    assert {"exercise", "sleep_hours", "alcohol", "social", "diet_quality", "work_stress", "g_steps"} <= keys
    assert all(t["source"] and t["url"].startswith("https://") for t in p["tips"])
    assert p["forecast"] == {"have": 0, "needed": 21}


def test_milestone_and_streak(client, auth_header):
    h, _ = auth_header()
    t = today_of(client, h)
    for i in (2, 1, 0):
        evening(client, h, t - timedelta(days=i))
    p = client.get("/progress", headers=h).json()
    assert p["days_logged"] == 3 and p["milestone"] == 3 and p["streak"] == 3


def test_behaviour_streaks(client, auth_header):
    h, _ = auth_header()
    t = today_of(client, h)
    evening(client, h, t - timedelta(days=3), exercise=0, alcohol=1)
    for i in (2, 1):
        evening(client, h, t - timedelta(days=i), exercise=1, alcohol=0)
    s = {x["key"]: x for x in client.get("/progress", headers=h).json()["behaviour_streaks"]}
    assert s["exercise"]["days"] == 2 and s["exercise"]["text"] == "Worked out 2 days in a row"
    assert s["alcohol"]["text"] == "2 alcohol-free days in a row"
    assert "social" not in s


def test_unlock_progress_and_tip_retires(client, auth_header):
    h, _ = auth_header()
    t = today_of(client, h)
    for i in range(10):
        evening(client, h, t - timedelta(days=i), exercise=i % 2)
    p = client.get("/progress", headers=h).json()
    ex = next(u for u in p["unlocks"] if u["key"] == "exercise")
    assert ex["have"] == {"with": 5, "without": 5} and ex["enough"]
    alc = next(u for u in p["unlocks"] if u["key"] == "alcohol")
    assert alc["have"] == {"with": 0, "without": 10} and not alc["enough"]
    tip_keys = {t["key"] for t in p["tips"]}
    assert "exercise" not in tip_keys and "alcohol" in tip_keys


def test_reminder_uses_general_tip_for_new_user(client, auth_header):
    from app.db import SessionLocal
    from app.reminders import send_due_reminders
    from app.tips import TIPS
    h, _ = auth_header()
    client.patch("/me", headers=h, json={"timezone": "UTC", "morning_reminder": "08:00"})
    client.post("/push/subscriptions", headers=h, json={"endpoint": f"https://push.example/{uuid.uuid4()}",
                                                        "keys": {"p256dh": "x", "auth": "y"}})
    uid = client.get("/me", headers=h).json()["user_id"]
    got = []
    t = today_of(client, h) + timedelta(days=1)
    with SessionLocal() as db:
        send_due_reminders(db, datetime.combine(t, time(8, 5), timezone.utc),
                           lambda sub, payload: got.append(payload) if str(sub.user_id) == uid else None)
    assert got and any(tip["short"] in got[-1]["body"] for tip in TIPS)
