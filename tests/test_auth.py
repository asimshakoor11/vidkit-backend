"""Comprehensive tests for authentication and owner rate limit bypass."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models.user import User


def test_signup_success(client: TestClient) -> None:
    """Signup creates a user, hashes password, normalizes email."""
    response = client.post(
        "/api/auth/signup",
        json={"email": "  TestUser@Example.COM  ", "password": "securepassword123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 180 * 60
    assert data["user"]["email"] == "testuser@example.com"
    assert data["user"]["plan"] == "free"
    assert data["user"]["is_owner"] is False

    # Check decoded token claims
    settings = get_settings()
    claims = jwt.decode(
        data["access_token"],
        settings.jwt_secret,
        algorithms=["HS256"],
        options={"verify_signature": True},
    )
    assert claims["email"] == "testuser@example.com"
    assert claims["sub"] == data["user"]["id"]
    assert claims["exp"] - claims["iat"] == 180 * 60


def test_signup_rejects_duplicate_email(client: TestClient) -> None:
    """Duplicate email registration returns 409 EMAIL_ALREADY_REGISTERED."""
    client.post(
        "/api/auth/signup",
        json={"email": "duplicate@example.com", "password": "password123"},
    )
    res = client.post(
        "/api/auth/signup",
        json={"email": "DUPLICATE@example.com", "password": "password123"},
    )
    assert res.status_code == 409
    body = res.json()
    assert body["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_signup_rejects_short_password(client: TestClient) -> None:
    """Password shorter than 8 chars is rejected."""
    res = client.post(
        "/api/auth/signup",
        json={"email": "short@example.com", "password": "short"},
    )
    assert res.status_code == 422


def test_login_success_and_failure(client: TestClient) -> None:
    """Login succeeds with correct password and fails with generic error for wrong credentials."""
    client.post(
        "/api/auth/signup",
        json={"email": "loginuser@example.com", "password": "password1234"},
    )

    # Success
    res = client.post(
        "/api/auth/login",
        json={"email": "LoginUser@example.com", "password": "password1234"},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()

    # Wrong password
    res = client.post(
        "/api/auth/login",
        json={"email": "loginuser@example.com", "password": "wrongpassword"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert res.json()["error"]["message"] == "Invalid email or password."

    # Non-existent user
    res = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@example.com", "password": "wrongpassword"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_token_expiration_follows_setting(client: TestClient) -> None:
    """Token lifetime honors jwt_expire_minutes setting."""
    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value = get_settings().model_copy(
            update={"jwt_expire_minutes": 60}
        )
        res = client.post(
            "/api/auth/signup",
            json={"email": "customexp@example.com", "password": "password123"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["expires_in"] == 3600
        claims = jwt.decode(
            data["access_token"],
            get_settings().jwt_secret,
            algorithms=["HS256"],
            options={"verify_signature": True},
        )
        assert claims["exp"] - claims["iat"] == 3600


def test_me_endpoint_with_valid_token(client: TestClient) -> None:
    """GET /api/auth/me returns user profile."""
    res = client.post(
        "/api/auth/signup",
        json={"email": "me@example.com", "password": "password123"},
    )
    token = res.json()["access_token"]

    res_me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_me.status_code == 200
    assert res_me.json()["email"] == "me@example.com"
    assert res_me.json()["is_owner"] is False


def test_me_endpoint_requires_token(client: TestClient) -> None:
    """GET /api/auth/me returns 401 UNAUTHORIZED when no token is passed."""
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_endpoint_expired_token(client: TestClient) -> None:
    """GET /api/auth/me returns 401 TOKEN_EXPIRED for expired token."""
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)
    expired_payload = {
        "sub": "some-id",
        "email": "expired@example.com",
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm="HS256")

    res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_logout(client: TestClient) -> None:
    """POST /api/auth/logout returns 204."""
    res = client.post("/api/auth/logout")
    assert res.status_code == 204


def test_rate_limiter_anonymous_and_user_hit_limit(client: TestClient) -> None:
    """Regular users hit rate limiter on limited endpoints like /api/video/info."""
    # Test on /api/video/info with invalid domain to trigger detect_platform_from_url or hit limit
    # The limiter on /api/video/info is 10/minute
    for _ in range(10):
        client.post("/api/video/info", json={"url": "https://youtube.com/watch?v=123"})

    # 11th request should be rate limited (429)
    res = client.post("/api/video/info", json={"url": "https://youtube.com/watch?v=123"})
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMITED"


def test_rate_limiter_owner_bypass(client: TestClient) -> None:
    """Owner with valid unexpired token bypasses rate limit completely."""
    settings = get_settings()
    owner_email = "owner@vidkit.test"
    with patch("app.core.rate_limit.get_settings") as mock_rate_settings, patch(
        "app.core.security.get_settings"
    ) as mock_sec_settings:
        custom_settings = settings.model_copy(update={"owner_email": owner_email})
        mock_rate_settings.return_value = custom_settings
        mock_sec_settings.return_value = custom_settings

        # Generate owner token directly or via signup
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "sub": "owner-uuid",
            "email": owner_email,
            "iat": int(now.timestamp()),
            "exp": int((now + datetime.timedelta(hours=3)).timestamp()),
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

        # Exceed standard rate limit (10/minute)
        for _ in range(15):
            res = client.post(
                "/api/video/info",
                json={"url": "https://youtube.com/watch?v=123"},
                headers={"Authorization": f"Bearer {token}"},
            )
            # Must NOT be 429
            assert res.status_code != 429


def test_rate_limiter_expired_owner_token_is_limited(client: TestClient) -> None:
    """Owner with expired token does NOT bypass rate limit and hits 429."""
    settings = get_settings()
    owner_email = "owner@vidkit.test"
    with patch("app.core.rate_limit.get_settings") as mock_rate_settings:
        custom_settings = settings.model_copy(update={"owner_email": owner_email})
        mock_rate_settings.return_value = custom_settings

        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)
        expired_payload = {
            "sub": "owner-uuid",
            "email": owner_email,
            "iat": int(past.timestamp()),
            "exp": int((past + datetime.timedelta(hours=1)).timestamp()),
        }
        expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm="HS256")

        for _ in range(10):
            client.post(
                "/api/video/info",
                json={"url": "https://youtube.com/watch?v=123"},
                headers={"Authorization": f"Bearer {expired_token}"},
            )

        res = client.post(
            "/api/video/info",
            json={"url": "https://youtube.com/watch?v=123"},
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert res.status_code == 429


def test_rate_limiter_forged_token_does_not_bypass(client: TestClient) -> None:
    """Token with wrong secret is treated as anonymous and rate-limited."""
    owner_email = "owner@vidkit.test"
    with patch("app.core.rate_limit.get_settings") as mock_rate_settings:
        custom_settings = get_settings().model_copy(update={"owner_email": owner_email})
        mock_rate_settings.return_value = custom_settings

        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "sub": "owner-uuid",
            "email": owner_email,
            "iat": int(now.timestamp()),
            "exp": int((now + datetime.timedelta(hours=3)).timestamp()),
        }
        forged_token = jwt.encode(payload, "wrong-forged-secret-key-12345678", algorithm="HS256")

        for _ in range(10):
            client.post(
                "/api/video/info",
                json={"url": "https://youtube.com/watch?v=123"},
                headers={"Authorization": f"Bearer {forged_token}"},
            )

        res = client.post(
            "/api/video/info",
            json={"url": "https://youtube.com/watch?v=123"},
            headers={"Authorization": f"Bearer {forged_token}"},
        )
        assert res.status_code == 429


def test_auth_endpoints_rate_limited_per_ip(client: TestClient) -> None:
    """Signup endpoint is rate limited (5/hour) per IP without owner bypass."""
    for i in range(5):
        res = client.post(
            "/api/auth/signup",
            json={"email": f"user{i}@example.com", "password": "password123"},
        )
        assert res.status_code in (201, 409)

    # 6th request must be rate limited
    res = client.post(
        "/api/auth/signup",
        json={"email": "overflow@example.com", "password": "password123"},
    )
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMITED"
