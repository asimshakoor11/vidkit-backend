"""Platform detection helpers."""

from __future__ import annotations

from app.core.security import detect_platform_from_url


def detect_platform(url: str) -> str:
    """Return the platform id for a supported video URL."""
    return detect_platform_from_url(url)
