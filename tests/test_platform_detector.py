"""Tests for platform detection and URL security."""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.core.security import detect_platform_from_url, sanitize_filename
from app.services.platform_detector import detect_platform


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://m.youtube.com/watch?v=abc", "youtube"),
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://vm.tiktok.com/ZMabcdef/", "tiktok"),
        ("https://www.instagram.com/reel/ABC123/", "instagram"),
        ("https://www.facebook.com/watch/?v=123", "facebook"),
        ("https://fb.watch/abcdef/", "facebook"),
    ],
)
def test_detect_supported_platforms(url: str, platform: str) -> None:
    assert detect_platform(url) == platform


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video",
        "ftp://youtube.com/watch?v=1",
        "https://127.0.0.1/video",
        "https://localhost/video",
        "not-a-url",
    ],
)
def test_reject_unsupported_or_ssrf(url: str) -> None:
    with pytest.raises(AppError) as exc:
        detect_platform_from_url(url)
    assert exc.value.code in {"INVALID_URL", "UNSUPPORTED_PLATFORM"}


def test_sanitize_filename_strips_paths() -> None:
    assert ".." not in sanitize_filename("../../etc/passwd")
    assert "/" not in sanitize_filename("a/b/c.mp4")
    assert sanitize_filename("my video (1).mp4").endswith(".mp4")
