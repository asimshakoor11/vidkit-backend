"""URL allow-list, SSRF guards, and filename sanitization."""

from __future__ import annotations

import re
from urllib.parse import urlparse

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
ALLOWED_UPLOAD_MIMES = {
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "video/x-msvideo",
    "video/avi",
    "application/octet-stream",
}

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


def sanitize_filename(name: str, fallback: str = "file") -> str:
    """Return a safe basename with no path traversal."""
    base = name.replace("\\", "/").split("/")[-1].strip()
    base = _UNSAFE_FILENAME.sub("_", base).strip("._")
    if not base or base in {".", ".."}:
        return fallback
    return base[:200]


def validate_upload_extension(filename: str) -> str:
    """Validate and return the lowercase extension including the dot."""
    safe = sanitize_filename(filename)
    lower = safe.lower()
    for ext in ALLOWED_UPLOAD_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    raise AppError(
        "UNSUPPORTED_FORMAT",
        "Unsupported file type. Allowed: MP4, MOV, MKV, WEBM.",
    )
