"""Verify Supabase access tokens.

The frontend logs in with Supabase (email or Google) and sends the access token
as `Authorization: Bearer <token>`. We only verify it here; we never see passwords.

Supports both Supabase signing setups:
- Asymmetric keys (default for new projects): verified against the public JWKS.
- Legacy shared secret (HS256): set SUPABASE_JWT_SECRET.
"""
import uuid
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

bearer = HTTPBearer(auto_error=False)

# The single user in local demo mode.
DEMO_USER_ID = uuid.UUID("00000000-0000-4000-8000-00000000d3e0")


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    url = f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(url, cache_keys=True)


def decode_token(token: str) -> dict:
    settings = get_settings()
    common = {"audience": "authenticated", "issuer": f"{settings.supabase_url}/auth/v1"}

    if settings.supabase_jwt_secret:
        return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], **common)

    key = _jwks_client().get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["ES256", "RS256"], **common)


def current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> uuid.UUID:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if get_settings().dev_mode:
        return DEMO_USER_ID
    if creds is None:
        raise unauthorized
    try:
        claims = decode_token(creds.credentials)
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
