from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import make_url

from app import entries, garmin, insights, profiles, progress, recommendations, reminders, stats
from app.config import get_settings

settings = get_settings()

# Demo mode skips login, so it must never run against a real (remote) database.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
if settings.dev_mode and make_url(settings.database_url).host not in LOCAL_HOSTS:
    raise RuntimeError("DEV_MODE is only allowed with a database on this machine. Refusing to start.")

app = FastAPI(title="NessWell API")
if settings.dev_mode:
    # Local demo: allow the app from this computer or a phone on the same wifi.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
        allow_methods=["*"], allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(profiles.router)
app.include_router(entries.router)
app.include_router(reminders.router)
app.include_router(stats.router)
app.include_router(insights.router)
app.include_router(recommendations.router)
app.include_router(garmin.router)
app.include_router(progress.router)


@app.get("/health")
def health():
    return {"ok": True, "demo": settings.dev_mode}
