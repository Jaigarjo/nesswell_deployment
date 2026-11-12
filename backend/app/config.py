from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    supabase_url: str = ""
    supabase_jwt_secret: str | None = None
    allowed_origins: str = "http://localhost:5173"

    # Web push (generate with scripts/gen_vapid.py)
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:you@example.com"

    # Fernet key for stored Garmin tokens (scripts/gen_garmin_key.py)
    garmin_token_key: str | None = None

    # Shared secret the scheduler sends to /internal/send-reminders
    cron_secret: str | None = None

    # Local demo mode: no Supabase, everyone is the demo user. Refuses to start
    # unless the database is on this machine (see app/main.py).
    dev_mode: bool = False

    # Hour (user's local time) before which a log counts toward the previous day.
    day_cutoff_hour: int = 4

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
