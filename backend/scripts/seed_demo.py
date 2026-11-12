"""Fill the local demo with ~3 months of realistic data so every screen has something to show.

Built-in patterns (so you can check the engine finds them):
- Drinking lowers the NEXT morning (about -1.3) and next night's HRV.
- Working out lifts that evening (about +1.4); runs a bit more than gym.
- Seeing people lifts evenings (about +0.8); work stress drags them down.
- More sleep means a better morning.

Usage (demo mode only):
    python scripts/seed_demo.py            # seed if empty
    python scripts/seed_demo.py --reset    # wipe the demo user and reseed
    python scripts/seed_demo.py --empty    # wipe and leave empty, to log from scratch
"""
import argparse
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
import os
import sys
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.auth import DEMO_USER_ID  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import DailyMetric, Entry, Profile  # noqa: E402

DAYS = 90
NOTES_EVENING = [
    "Long day, but a good dinner with friends.", "Deadline stress all afternoon.",
    "Quiet one. Read and went to bed early.", "Great session, felt strong.",
    "Meetings back to back, no time to think.", "Beach walk after work.",
]
NOTES_MORNING = ["Woke up before the alarm.", "Groggy.", "Slept through, felt rested.", "Neighbours were loud."]
EXERCISE = ["Run", "Gym", "Surf", "Yoga", "Cycle", "Walk"]
FOOD = ["Home-cooked", "Takeaway", "Fruit and veg", "Protein", "Sweets", "Caffeine", "Processed"]


def clip(x, lo, hi):
    return float(min(hi, max(lo, x)))


def wipe(db):
    db.execute(delete(Entry).where(Entry.user_id == DEMO_USER_ID))
    db.execute(delete(DailyMetric).where(DailyMetric.user_id == DEMO_USER_ID))
    db.execute(delete(Profile).where(Profile.user_id == DEMO_USER_ID))  # cascades experiments etc.
    db.commit()


def seed(client: TestClient, today: date, rng: np.random.Generator) -> int:
    n = 0
    prev_evening, prev_alcohol, prev_sleep = 6.0, 0, 7.0
    metrics = []
    for i in range(DAYS - 1, -1, -1):
        d = today - timedelta(days=i)
        weekend = d.weekday() >= 5
        friday_or_sat = d.weekday() in (4, 5)

        # ----- morning -----
        sleep = clip(round((rng.normal(7.1, 0.8) + (0.6 if weekend else 0) - 0.5 * prev_alcohol) * 2) / 2, 4.5, 9.5)
        sleep_q = int(clip(round(3 + 0.8 * (sleep - 7) - 0.8 * prev_alcohol + rng.normal(0, 0.7)), 1, 5))
        morning = 3 + 0.45 * sleep + 0.3 * (prev_evening - 6) - 1.3 * prev_alcohol + rng.normal(0, 0.6)
        if rng.random() > 0.06 and i != 0:  # leave today's morning for you to log
            body = {"score": int(clip(round(morning), 1, 10)),
                    "values": {"sleep_hours": sleep, "sleep_quality": sleep_q}}
            if rng.random() < 0.3:
                body["details"] = {"sleep_hours": {"data": {"bedtime": f"{int(22 + rng.integers(0, 3)) % 24:02d}:{rng.choice(['00', '15', '30', '45'])}"}}}
            if rng.random() < 0.12:
                body["note"] = str(rng.choice(NOTES_MORNING))
            client.put(f"/entries/{d}/morning", json=body).raise_for_status()
            n += 1

        # ----- evening -----
        exercise = int(rng.random() < 0.45)
        social = int(rng.random() < (0.7 if weekend else 0.35))
        alcohol = int(rng.random() < (0.55 if friday_or_sat else 0.15))
        stress = int(clip(round(rng.normal(1.6 if weekend else 3.2, 0.9)), 1, 5))
        diet = int(clip(round(rng.normal(3.4 - 0.7 * alcohol, 0.8)), 1, 5))
        kind = str(rng.choice(EXERCISE)) if exercise else None
        evening = (5 + 1.4 * exercise + (0.5 if kind == "Run" else 0) + 0.8 * social
                   - 0.45 * (stress - 3) + 0.3 * (diet - 3) + rng.normal(0, 0.7))
        if rng.random() > 0.08 and i != 0:  # leave tonight for you to log
            details = {}
            if exercise:
                details["exercise"] = {"data": {"type": kind, "minutes": int(rng.choice([20, 30, 45, 60, 90])),
                                                "intensity": str(rng.choice(["Easy", "Moderate", "Hard"]))}}
            if alcohol:
                details["alcohol"] = {"data": {"drinks": int(rng.integers(1, 7)),
                                               "type": [str(rng.choice(["Beer", "Wine", "Cocktails"]))]}}
            if not weekend:
                details["work_stress"] = {"data": {"hours": float(clip(round(rng.normal(8.5, 1.2) * 2) / 2, 5, 12))}}
            if rng.random() < 0.5:
                details["diet_quality"] = {"data": {"amount": str(rng.choice(["About right", "About right", "Too much"])),
                                                    "food": sorted(set(rng.choice(FOOD, size=2).tolist()))}}
            body = {"score": int(clip(round(evening), 1, 10)), "details": details,
                    "values": {"exercise": exercise, "social": social, "alcohol": alcohol,
                               "work_stress": stress, "diet_quality": diet}}
            if rng.random() < 0.2:
                body["note"] = str(rng.choice(NOTES_EVENING))
            client.put(f"/entries/{d}/evening", json=body).raise_for_status()
            n += 1

        # ----- Garmin-style metrics -----
        metrics.append(dict(day=d, g_sleep_hours=round(sleep + rng.normal(0, 0.25), 2),
                            g_sleep_score=clip(round(70 + 8 * (sleep - 7) - 8 * prev_alcohol + rng.normal(0, 6)), 20, 99),
                            g_hrv=clip(round(52 + 3 * (sleep - 7) - 7 * prev_alcohol + rng.normal(0, 4)), 20, 120),
                            g_resting_hr=clip(round(55 + 3 * prev_alcohol + rng.normal(0, 2)), 40, 80),
                            g_body_battery=clip(round(70 + 6 * (sleep - 7) - 10 * prev_alcohol + rng.normal(0, 7)), 5, 100),
                            g_stress=clip(round(22 + 6 * stress + rng.normal(0, 5)), 5, 90),
                            g_steps=clip(round(6500 + 5000 * exercise + rng.normal(0, 1800)), 800, 30000)))
        prev_evening, prev_alcohol, prev_sleep = evening, alcohol, sleep

    with SessionLocal() as db:
        for m in metrics:
            day = m.pop("day")
            for k, v in m.items():
                db.merge(DailyMetric(user_id=DEMO_USER_ID, day=day, key=k, value=v))
        db.commit()
    return n


def local_timezone() -> str:
    """This computer's IANA timezone (e.g. Australia/Sydney), falling back to UTC."""
    if os.environ.get("DEMO_TIMEZONE"):
        return os.environ["DEMO_TIMEZONE"]
    target = os.path.realpath("/etc/localtime")  # macOS and Linux
    return target.split("zoneinfo/", 1)[1] if "zoneinfo/" in target else "UTC"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe the demo user and reseed")
    ap.add_argument("--empty", action="store_true", help="wipe and leave empty")
    args = ap.parse_args()

    if not get_settings().dev_mode:
        sys.exit("Refusing to run: DEV_MODE is off. This script is for the local demo only.")

    from app.main import app
    client = TestClient(app)

    with SessionLocal() as db:
        existing = db.scalar(select(Entry.id).where(Entry.user_id == DEMO_USER_ID).limit(1))
        if args.reset or args.empty:
            wipe(db)
        elif existing:
            print("Demo data already there. Use --reset to start over, or --empty for a clean slate.")
            return

    if args.empty:
        print("Demo user wiped. Log from scratch.")
        return

    tz = local_timezone()
    client.patch("/me", json={"timezone": tz, "morning_reminder": "08:00", "evening_reminder": "21:30"}).raise_for_status()
    today = date.fromisoformat(client.get("/me").json()["today"])
    n = seed(client, today, np.random.default_rng(42))
    r = client.post("/experiments", json={"key": "exercise", "target": "evening", "lag": 0, "goal_days": 4})
    print(f"Seeded {n} check-ins over {DAYS} days, plus Garmin-style metrics"
          f"{' and a running experiment' if r.status_code == 201 else ''}. Today's check-ins are left for you.")


if __name__ == "__main__":
    main()
