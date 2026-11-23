"""URL allow-list, SSRF guards, and filename sanitization."""

from __future__ import annotations

import ipaddress
import re
import socket
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import Request, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.models.user import User

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plain text password using Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    """Verify password against Argon2 hash, safe against empty or invalid hashes."""
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(
    user_id: str, email: str, expires_delta: timedelta | None = None
) -> tuple[str, int]:
    """
    Generate HS256 JWT access token with claims sub, email, iat, exp.
    Returns (token, expires_in_seconds).
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    exp = now + delta
    payload = {
        "sub": str(user_id),
        "email": email.strip().lower(),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    expires_in = int(delta.total_seconds())
    return token, expires_in


def is_owner(user_or_claims: Any) -> bool:
    """
    True only if OWNER_EMAIL is set and the email matches it
    (case-insensitive, compared with hmac.compare_digest).
    """
    settings = get_settings()
    if not settings.owner_email or not settings.owner_email.strip():
        return False
    
    email = None
    if isinstance(user_or_claims, dict):
        email = user_or_claims.get("email")
    elif hasattr(user_or_claims, "email"):
        email = getattr(user_or_claims, "email")
    elif isinstance(user_or_claims, str):
        email = user_or_claims

    if not email or not isinstance(email, str):
        return False

    return hmac.compare_digest(email.strip().lower(), settings.owner_email.strip().lower())


def extract_bearer_token(request: Request) -> str | None:
    """Extract bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    parts = auth_header.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    """
    Returns the user or None.
    Never raises for a missing, invalid or expired token.
    """
    token = extract_bearer_token(request)
    if not token:
        return None
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "iat"]},
        )
    except Exception:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = db.scalar(select(User).where(User.id == str(user_id)))
    if not user or not user.is_active:
        return None
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    Raises 401 if not authenticated.
    When expired, returns 401 with code TOKEN_EXPIRED;
    Other invalid or missing tokens return 401 with code UNAUTHORIZED.
    """
    token = extract_bearer_token(request)
    if not token:
        raise AppError("UNAUTHORIZED", "Authentication required.", status_code=401)
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "iat"]},
        )
    except jwt.ExpiredSignatureError:
        raise AppError("TOKEN_EXPIRED", "Token has expired.", status_code=401)
    except Exception:
        raise AppError("UNAUTHORIZED", "Invalid token.", status_code=401)

    user_id = payload.get("sub")
    if not user_id:
        raise AppError("UNAUTHORIZED", "Invalid token subject.", status_code=401)

    user = db.scalar(select(User).where(User.id == str(user_id)))
    if not user or not user.is_active:
        raise AppError("UNAUTHORIZED", "User not found or inactive.", status_code=401)
    return user


from app.core.errors import AppError

PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "youtube": (
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    ),
    "tiktok": (
        "tiktok.com",
        "www.tiktok.com",
        "vm.tiktok.com",
        "m.tiktok.com",
    ),
    "instagram": (
        "instagram.com",
        "www.instagram.com",
    ),
    "facebook": (
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "fb.watch",
        "www.fb.watch",
    ),
}

ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".avif",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}
ALLOWED_PDF_EXTENSIONS = {".pdf"}
ALLOWED_IMAGE_OR_PDF_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_PDF_EXTENSIONS
ALLOWED_DOC_EXTENSIONS = {".docx"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".opus"}

_UNSAFE_FILENAME = re.compile(r"[^\w.\-]+", re.UNICODE)


def _hostname_matches(host: str, allowed: str) -> bool:
    host = host.lower().rstrip(".")
    allowed = allowed.lower()
    return host == allowed or host.endswith("." + allowed)


def detect_platform_from_url(url: str) -> str:
    """
    Detect a supported platform from a URL.

    Raises AppError for invalid schemes or unsupported hosts.
    """
    try:
        parsed = urlparse(url.strip())
    except Exception as exc:  # noqa: BLE001
        raise AppError("INVALID_URL", "Please enter a valid URL.") from exc

    if parsed.scheme not in {"http", "https"}:
        raise AppError("INVALID_URL", "Only http and https URLs are supported.")

    host = parsed.hostname
    if not host:
        raise AppError("INVALID_URL", "Please enter a valid URL.")

    # Block obvious SSRF targets (raw IPs / localhost)
    if host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127."):
        raise AppError("INVALID_URL", "This URL is not allowed.")
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        raise AppError("INVALID_URL", "This URL is not allowed.")

    for platform, domains in PLATFORM_DOMAINS.items():
        if any(_hostname_matches(host, domain) for domain in domains):
            return platform

    raise AppError(
        "UNSUPPORTED_PLATFORM",
        "Unsupported platform. Try a YouTube, TikTok, Instagram or Facebook link.",
    )


def validate_public_http_url(url: str) -> str:
    """
    Validate a shorten/redirect target: http(s) only, no localhost/private IPs.
    Returns the stripped URL.
    """
    raw = (url or "").strip()
    try:
        parsed = urlparse(raw)
    except Exception as exc:  # noqa: BLE001
        raise AppError("INVALID_URL", "Please enter a valid URL.") from exc

    if parsed.scheme not in {"http", "https"}:
        raise AppError("INVALID_URL", "Only http and https URLs are supported.")
    host = parsed.hostname
    if not host:
        raise AppError("INVALID_URL", "Please enter a valid URL.")

    lowered = host.lower().rstrip(".")
    if lowered in {"localhost", "127.0.0.1", "::1"} or lowered.endswith(".localhost"):
        raise AppError("INVALID_URL", "This URL is not allowed.")
    if lowered.startswith("127.") or lowered.endswith(".local"):
        raise AppError("INVALID_URL", "This URL is not allowed.")

    # Block literal IPs that are private / reserved
    try:
        ip = ipaddress.ip_address(lowered)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise AppError("INVALID_URL", "This URL is not allowed.")
    except ValueError:
        # Hostname — resolve and reject private answers (best-effort SSRF guard)
        try:
            infos = socket.getaddrinfo(lowered, None)
        except socket.gaierror:
            infos = []
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise AppError("INVALID_URL", "This URL is not allowed.")

    return raw


def sanitize_filename(name: str, fallback: str = "file") -> str:
    """Return a safe basename with no path traversal."""
    base = name.replace("\\", "/").split("/")[-1].strip()
    base = _UNSAFE_FILENAME.sub("_", base).strip("._")
    if not base or base in {".", ".."}:
        return fallback
    return base[:200]


def _match_extension(filename: str, allowed: set[str]) -> str | None:
    lower = sanitize_filename(filename).lower()
    for ext in allowed:
        if lower.endswith(ext):
            return ext
    return None


def validate_upload_extension(filename: str) -> str:
    """Validate and return the lowercase video extension including the dot."""
    ext = _match_extension(filename, ALLOWED_UPLOAD_EXTENSIONS)
    if ext:
        return ext
    raise AppError(
        "UNSUPPORTED_FORMAT",
        "Unsupported file type. Allowed: MP4, MOV, MKV, WEBM, AVI.",
    )


def validate_image_extension(filename: str, *, allow_pdf: bool = False) -> str:
    """Validate and return the lowercase image (or PDF) extension."""
    allowed = ALLOWED_IMAGE_OR_PDF_EXTENSIONS if allow_pdf else ALLOWED_IMAGE_EXTENSIONS
    ext = _match_extension(filename, allowed)
    if ext:
        return ext
    kinds = "JPG, PNG, WEBP, AVIF, GIF, BMP, TIFF"
    if allow_pdf:
        kinds += ", PDF"
    raise AppError("UNSUPPORTED_FORMAT", f"Unsupported file type. Allowed: {kinds}.")


def validate_pdf_extension(filename: str) -> str:
    """Validate and return the lowercase .pdf extension."""
    ext = _match_extension(filename, ALLOWED_PDF_EXTENSIONS)
    if ext:
        return ext
    raise AppError("UNSUPPORTED_FORMAT", "Unsupported file type. Allowed: PDF.")


def validate_doc_extension(filename: str) -> str:
    """Validate and return the lowercase .docx extension."""
    ext = _match_extension(filename, ALLOWED_DOC_EXTENSIONS)
    if ext:
        return ext
    raise AppError("UNSUPPORTED_FORMAT", "Unsupported file type. Allowed: DOCX.")


def validate_audio_extension(filename: str) -> str:
    """Validate and return the lowercase audio extension."""
    ext = _match_extension(filename, ALLOWED_AUDIO_EXTENSIONS)
    if ext:
        return ext
    raise AppError(
        "UNSUPPORTED_FORMAT",
        "Unsupported file type. Allowed: MP3, WAV, AAC, M4A, FLAC, OGG, OPUS.",
    )
