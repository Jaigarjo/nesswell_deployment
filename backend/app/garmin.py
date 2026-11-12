"""Garmin Connect sync via the unofficial python-garminconnect library.

Security:
- The Garmin password is used once, in memory, to log in. It is never stored or logged.
- The resulting OAuth tokens are encrypted (Fernet, GARMIN_TOKEN_KEY) before they
  touch the database. Refreshed tokens are re-encrypted after every sync.

MFA: the library keeps a half-finished MFA login inside the client object, so it's
held in memory for a few minutes between "enter password" and "enter code". That
works on a single server instance; if the server restarts in between, the user
simply starts again.

This is unofficial access. Garmin can change things and break it; if that happens,
check for a newer garminconnect release first.
"""
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models import DailyMetric, GarminConnection
from app.profiles import ensure_profile, user_today

log = logging.getLogger(__name__)
router = APIRouter()

BACKFILL_DAYS = 30      # on first connect
RECENT_DAYS = 3         # each regular sync re-reads a few days; late watch uploads land
SYNC_EVERY = timedelta(hours=3)
MFA_TTL_SECONDS = 300


# ---------- client factory (tests replace this) ----------

def _real_client(email: str | None = None, password: str | None = None, return_on_mfa: bool = False):
    from garminconnect import Garmin
    return Garmin(email, password, return_on_mfa=return_on_mfa)


client_factory: Callable[..., Any] = _real_client


def _errors():
    from garminconnect import (GarminConnectAuthenticationError, GarminConnectConnectionError,
                               GarminConnectTooManyRequestsError)
    return GarminConnectAuthenticationError, GarminConnectConnectionError, GarminConnectTooManyRequestsError


# ---------- encryption ----------

def _fernet() -> Fernet:
    key = get_settings().garmin_token_key
    if not key:
        raise HTTPException(503, "Garmin isn't set up on the server (GARMIN_TOKEN_KEY missing)")
    return Fernet(key.encode())


def encrypt(tokens_json: str) -> str:
    return _fernet().encrypt(tokens_json.encode()).decode()


def decrypt(blob: str) -> str:
    return _fernet().decrypt(blob.encode()).decode()


# ---------- pending MFA logins (in memory) ----------

_pending: dict[uuid.UUID, tuple[Any, float]] = {}
_pending_lock = threading.Lock()


def _put_pending(user_id: uuid.UUID, client: Any) -> None:
    with _pending_lock:
        now = time.monotonic()
        for k in [k for k, (_, t) in _pending.items() if now - t > MFA_TTL_SECONDS]:
            del _pending[k]
        _pending[user_id] = (client, now)


def _pop_pending(user_id: uuid.UUID) -> Any | None:
    with _pending_lock:
        item = _pending.pop(user_id, None)
    if item and time.monotonic() - item[1] <= MFA_TTL_SECONDS:
        return item[0]
    return None


# ---------- reading Garmin's responses ----------

def _dig(d: Any, *path: str) -> Any:
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _ok(v: Any, lo: float = 0) -> float | None:
    """Garmin uses negative numbers (-1, -2) for 'not enough data'."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v >= lo else None


def extract_day(client: Any, day: date) -> dict[str, float]:
    """Pull one day's metrics. Each call is independent, so one missing endpoint doesn't lose the rest."""
    d = day.isoformat()
    out: dict[str, float | None] = {}

    def safe(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001  one failing metric shouldn't sink the day
            if type(e).__name__ in ("GarminConnectTooManyRequestsError", "GarminConnectAuthenticationError"):
                raise
            log.info("garmin %s failed for %s: %s", getattr(fn, "__name__", "call"), d, type(e).__name__)
            return None

    sleep = safe(lambda: client.get_sleep_data(d)) or {}
    secs = _ok(_dig(sleep, "dailySleepDTO", "sleepTimeSeconds"), 1)
    out["g_sleep_hours"] = round(secs / 3600, 2) if secs else None
    out["g_sleep_score"] = _ok(_dig(sleep, "dailySleepDTO", "sleepScores", "overall", "value"))

    hrv = safe(lambda: client.get_hrv_data(d)) or {}
    out["g_hrv"] = _ok(_dig(hrv, "hrvSummary", "lastNightAvg"), 1)

    stats = safe(lambda: client.get_stats(d)) or {}
    out["g_resting_hr"] = _ok(stats.get("restingHeartRate"), 20)
    out["g_stress"] = _ok(stats.get("averageStressLevel"))
    out["g_steps"] = _ok(stats.get("totalSteps"))
    out["g_body_battery"] = _ok(stats.get("bodyBatteryAtWakeTime")) or _ok(stats.get("bodyBatteryHighestValue"))

    return {k: v for k, v in out.items() if v is not None}


# ---------- sync ----------

def _store_tokens(db: Session, user_id: uuid.UUID, client: Any) -> None:
    values = dict(user_id=user_id, tokens_enc=encrypt(client.client.dumps()), status="connected", last_error=None)
    db.execute(insert(GarminConnection).values(**values)
               .on_conflict_do_update(index_elements=["user_id"], set_=values))
    db.commit()


def sync_user(db: Session, conn: GarminConnection, days: int, today: date) -> int:
    """Sync the last `days` days for one user. Returns how many values were written."""
    AuthError, ConnError, TooMany = _errors()
    try:
        client = client_factory()
        client.login(tokenstore=decrypt(conn.tokens_enc))
    except ConnError:
        conn.last_error = "Couldn't reach Garmin. It'll retry later."
        db.commit()
        return 0
    except (AuthError, InvalidToken) as e:
        conn.status, conn.last_error = "reauth", "Garmin needs you to sign in again."
        db.commit()
        log.info("garmin reauth needed for %s: %s", conn.user_id, type(e).__name__)
        return 0

    written = 0
    try:
        for i in range(days):
            day = today - timedelta(days=i)
            metrics = extract_day(client, day)
            for key, value in metrics.items():
                db.execute(insert(DailyMetric).values(user_id=conn.user_id, day=day, key=key, value=value)
                           .on_conflict_do_update(index_elements=["user_id", "day", "key"], set_={"value": value}))
                written += 1
    except TooMany:
        conn.last_error = "Garmin is rate-limiting requests. It'll retry later."
        db.commit()
        raise
    except AuthError:
        conn.status, conn.last_error = "reauth", "Garmin needs you to sign in again."
        db.commit()
        return written

    # Tokens may have been refreshed during the calls: keep the newest.
    conn.tokens_enc = encrypt(client.client.dumps())
    conn.status, conn.last_error = "connected", None
    conn.last_sync_at = datetime.now(timezone.utc)
    db.commit()
    return written


def _backfill(user_id: uuid.UUID) -> None:
    """Runs after the connect response is sent, so the user isn't kept waiting."""
    with SessionLocal() as db:
        conn = db.get(GarminConnection, user_id)
        if conn is None:
            return
        try:
            today = user_today(ensure_profile(db, user_id))
            sync_user(db, conn, BACKFILL_DAYS, today)
        except Exception:
            log.exception("garmin backfill failed for %s", user_id)


# ---------- endpoints ----------

class ConnectIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class MfaIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


def _status(conn: GarminConnection | None) -> dict:
    if conn is None:
        return {"connected": False}
    return {
        "connected": True, "status": conn.status, "last_error": conn.last_error,
        "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
    }


@router.get("/garmin")
def garmin_status(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    return _status(db.get(GarminConnection, user_id))


@router.post("/garmin/connect")
def garmin_connect(body: ConnectIn, background: BackgroundTasks,
                   user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    _fernet()  # fail fast if the server isn't configured
    ensure_profile(db, user_id)
    AuthError, ConnError, TooMany = _errors()
    client = client_factory(body.email, body.password, return_on_mfa=True)
    try:
        status, _ = client.login()
    except AuthError:
        raise HTTPException(400, "Garmin didn't accept that email and password.")
    except TooMany:
        raise HTTPException(429, "Garmin is limiting login attempts. Wait a few minutes and try again.")
    except ConnError:
        raise HTTPException(502, "Couldn't reach Garmin. Try again in a moment.")
    if status == "needs_mfa":
        _put_pending(user_id, client)
        return {"status": "needs_mfa"}
    _store_tokens(db, user_id, client)
    background.add_task(_backfill, user_id)
    return {"status": "connected"}


@router.post("/garmin/mfa")
def garmin_mfa(body: MfaIn, background: BackgroundTasks,
               user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    client = _pop_pending(user_id)
    if client is None:
        raise HTTPException(410, "That sign-in expired. Enter your Garmin email and password again.")
    AuthError, ConnError, _ = _errors()
    try:
        client.resume_login(None, body.code.strip())
    except (AuthError, ConnError):
        _put_pending(user_id, client)  # a wrong code can be retried on the same session
        raise HTTPException(400, "That code didn't work. Check it and try again.")
    _store_tokens(db, user_id, client)
    background.add_task(_backfill, user_id)
    return {"status": "connected"}


@router.post("/garmin/sync")
def garmin_sync_now(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    conn = db.get(GarminConnection, user_id)
    if conn is None:
        raise HTTPException(404, "Garmin isn't connected")
    _, _, TooMany = _errors()
    try:
        written = sync_user(db, conn, RECENT_DAYS, user_today(ensure_profile(db, user_id)))
    except TooMany:
        raise HTTPException(429, "Garmin is rate-limiting requests. Try again later.")
    return {**_status(conn), "written": written}


@router.delete("/garmin", status_code=204)
def garmin_disconnect(delete_data: bool = False,
                      user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    db.execute(delete(GarminConnection).where(GarminConnection.user_id == user_id))
    if delete_data:
        db.execute(delete(DailyMetric).where(DailyMetric.user_id == user_id))
    db.commit()


@router.get("/metrics")
def list_metrics(start: date, end: date,
                 user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)):
    rows = db.execute(select(DailyMetric.day, DailyMetric.key, DailyMetric.value)
                      .where(DailyMetric.user_id == user_id, DailyMetric.day.between(start, end))).all()
    out: dict[str, dict[str, float]] = {}
    for day, key, value in rows:
        out.setdefault(day.isoformat(), {})[key] = float(value)
    return out


@router.post("/internal/sync-garmin")
def cron_sync_garmin(x_cron_secret: str = Header(default=""), db: Session = Depends(get_db)):
    import secrets
    expected = get_settings().cron_secret
    if not expected:
        raise HTTPException(503, "CRON_SECRET isn't set")
    if not secrets.compare_digest(x_cron_secret, expected):
        raise HTTPException(403, "Wrong cron secret")

    _, _, TooMany = _errors()
    cutoff = datetime.now(timezone.utc) - SYNC_EVERY
    due = db.scalars(select(GarminConnection).where(
        GarminConnection.status == "connected",
        (GarminConnection.last_sync_at.is_(None)) | (GarminConnection.last_sync_at < cutoff),
    )).all()
    stats = {"users": 0, "written": 0, "rate_limited": False}
    for conn in due:
        try:
            stats["written"] += sync_user(db, conn, RECENT_DAYS, user_today(ensure_profile(db, conn.user_id)))
            stats["users"] += 1
        except TooMany:
            stats["rate_limited"] = True
            break  # back off entirely; the next run picks up where we stopped
        except Exception:
            log.exception("garmin sync failed for %s", conn.user_id)
            db.rollback()
    return stats
