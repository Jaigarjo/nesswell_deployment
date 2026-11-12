import os
import time
import uuid

import jwt
import pytest

# Test config must be set before the app is imported.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/wellness_test")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-at-least-32-characters-long")
os.environ.setdefault("GARMIN_TOKEN_KEY", "0cKt1d1yX9o3m8tZ2i8a0YV8v5u1eO2k3Qb8m1b9H0M=")
os.environ.setdefault("CRON_SECRET", "test-cron-secret")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def make_token(user_id: uuid.UUID, **overrides) -> str:
    claims = {
        "sub": str(user_id),
        "aud": "authenticated",
        "iss": f"{os.environ['SUPABASE_URL']}/auth/v1",
        "exp": int(time.time()) + 3600,
        **overrides,
    }
    return jwt.encode(claims, os.environ["SUPABASE_JWT_SECRET"], algorithm="HS256")


@pytest.fixture
def auth_header():
    def _make(user_id: uuid.UUID | None = None, **overrides):
        uid = user_id or uuid.uuid4()
        return {"Authorization": f"Bearer {make_token(uid, **overrides)}"}, uid
    return _make
