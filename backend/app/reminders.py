"""Web push reminders.

Render's free tier sleeps, so nothing inside the API can run on a timer.
Instead an external scheduler (GitHub Actions, see .github/workflows/reminders.yml)
calls POST /internal/send-reminders every 15 minutes. Each call sends whatever
is due right now and records it, so repeated or overlapping calls are harmless.
"""
import json
import logging
import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.config import get_settings
from app.days import reminder_due
from app.db import get_db
from app.models import Entry, Profile, PushSubscription
from app.profiles import ensure_profile

log = logging.getLogger(__name__)
router = APIRouter()

MESSAGES = {
    "morning": {"title": "Morning check-in", "body": "How did you sleep? It takes 20 seconds."},
    "evening": {"title": "Evening check-in", "body": "How was today?"},
}


class Gone(Exception):
    """The push service says this subscription no longer exists."""


def send_push(sub: PushSubscription, payload: dict) -> None:
    s = get_settings()
    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint,
                               "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps(payload),
            vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject},  # fresh dict: pywebpush mutates it
            ttl=3 * 3600,
        )
    except WebPushException as e:
        if e.response is not None and e.response.status_code in (404, 410):
            raise Gone from e
        raise


def send_due_reminders(
    db: Session,
    now: datetime | None = None,
    sender: Callable[[PushSubscription, dict], None] = send_push,
) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = get_settings().day_cutoff_hour
    stats = {"sent": 0, "skipped_logged": 0, "removed_subscriptions": 0, "errors": 0}

    profiles = db.scalars(
        select(Profile).where(
            or_(Profile.morning_reminder.is_not(None), Profile.evening_reminder.is_not(None)),
            exists().where(PushSubscription.user_id == Profile.user_id),
        )
    ).all()

    for p in profiles:
        for kind in ("morning", "evening"):
            at = getattr(p, f"{kind}_reminder")
            if at is None:
                continue
            day = reminder_due(now, p.timezone, at, cutoff)
            if day is None or getattr(p, f"last_{kind}_sent") == day:
                continue
            setattr(p, f"last_{kind}_sent", day)

            already_logged = db.scalar(select(exists().where(
                Entry.user_id == p.user_id, Entry.day == day, Entry.kind == kind)))
            if already_logged:
                stats["skipped_logged"] += 1
                continue

            try:  # personalise with the experiment or a tip; never let that block the reminder
                from app.recommendations import reminder_message
                message = reminder_message(db, p, kind, day, MESSAGES[kind])
            except Exception:
                log.exception("personalising reminder failed")
                db.rollback()
                setattr(p, f"last_{kind}_sent", day)  # rollback undid this; keep it so we don't resend
                message = MESSAGES[kind]
            payload = {**message, "url": f"/?kind={kind}&day={day.isoformat()}"}
            subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == p.user_id))
            for sub in subs:
                try:
                    sender(sub, payload)
                    stats["sent"] += 1
                except Gone:
                    db.delete(sub)
                    stats["removed_subscriptions"] += 1
                except Exception:
                    log.exception("push failed for subscription %s", sub.id)
                    stats["errors"] += 1
        db.commit()  # per user, so one failure doesn't resend to everyone
    return stats


# ---------- endpoints ----------

class SubscriptionIn(BaseModel):
    endpoint: str
    keys: dict[str, str]  # {"p256dh": ..., "auth": ...} straight from PushSubscription.toJSON()


class EndpointIn(BaseModel):
    endpoint: str


@router.get("/push/public-key")
def public_key():
    key = get_settings().vapid_public_key
    if not key:
        raise HTTPException(503, "Push isn't configured on the server")
    return {"key": key}


@router.post("/push/subscriptions", status_code=204)
def subscribe(
    body: SubscriptionIn,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    if "p256dh" not in body.keys or "auth" not in body.keys:
        raise HTTPException(422, "keys must include p256dh and auth")
    ensure_profile(db, user_id)
    values = dict(user_id=user_id, endpoint=body.endpoint,
                  p256dh=body.keys["p256dh"], auth=body.keys["auth"])
    db.execute(
        insert(PushSubscription).values(**values)
        .on_conflict_do_update(index_elements=["endpoint"], set_=values)
    )
    db.commit()


@router.delete("/push/subscriptions", status_code=204)
def unsubscribe(
    body: EndpointIn,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
):
    db.execute(delete(PushSubscription).where(
        PushSubscription.user_id == user_id, PushSubscription.endpoint == body.endpoint))
    db.commit()


@router.post("/push/test")
def test_push(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    """Send a test notification to all of this user's devices."""
    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)).all()
    if not subs:
        raise HTTPException(404, "No devices have notifications turned on")
    sent = 0
    for sub in subs:
        try:
            send_push(sub, {"title": "Notifications are on", "body": "You'll get your reminders here.", "url": "/"})
            sent += 1
        except Gone:
            db.delete(sub)
    db.commit()
    return {"sent": sent}


@router.post("/internal/send-reminders")
def cron_send_reminders(
    x_cron_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    expected = get_settings().cron_secret
    if not expected:
        raise HTTPException(503, "CRON_SECRET isn't set")
    if not secrets.compare_digest(x_cron_secret, expected):
        raise HTTPException(403, "Wrong cron secret")
    return send_due_reminders(db)
