"""Shared SlowAPI rate limiter instance with Owner bypass."""

from __future__ import annotations

import hmac
import uuid
import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings


def get_rate_limit_key(request: Request) -> str:
    """
    Key function for slowapi.
    - Decodes Bearer token without hitting database (signature + expiry + email claim).
    - If valid, unexpired, and matches OWNER_EMAIL: return a fresh UUID so it never hits the limit.
    - Otherwise fallback to client IP.
    """
    settings = get_settings()
    auth_header = request.headers.get("Authorization")
    if auth_header and settings.owner_email and settings.owner_email.strip():
        parts = auth_header.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            try:
                payload = jwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=["HS256"],
                    options={"require": ["exp", "email"]},
                )
                email = payload.get("email")
                if (
                    isinstance(email, str)
                    and hmac.compare_digest(
                        email.strip().lower(), settings.owner_email.strip().lower()
                    )
                ):
                    return f"owner-bypass:{uuid.uuid4()}"
            except Exception:
                # Expired, forged, or invalid token falls back to remote address
                pass

    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key, default_limits=[])
