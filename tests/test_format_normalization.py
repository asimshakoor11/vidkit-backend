"""Tests for yt-dlp format normalization."""

from __future__ import annotations

from app.services.downloader import format_selector, normalize_formats


def test_normalize_formats_picks_heights_and_audio() -> None:
    raw = [
        {"format_id": "1", "height": 1080, "width": 1920, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 50_000_000},
        {"format_id": "2", "height": 720, "width": 1280, "ext": "webm", "vcodec": "vp9", "acodec": "none", "filesize": 30_000_000},
        {"format_id": "3", "height": 720, "width": 1280, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 28_000_000},
        {"format_id": "4", "height": 480, "width": 854, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 15_000_000},
        {"format_id": "5", "height": 360, "width": 640, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 8_000_000},
        {"format_id": "6", "height": None, "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "filesize": 3_000_000},
        {"format_id": "7", "height": 144, "width": 256, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 1_000_000},
    ]
    formats = normalize_formats(raw)
    ids = [f.format_id for f in formats]
    assert ids == ["1080p", "720p", "480p", "360p", "audio"]
    assert formats[0].kind == "video"
    assert formats[0].ext == "mp4"
    assert formats[-1].kind == "audio"
    assert formats[-1].ext == "mp3"
    assert formats[1].filesize_bytes == 28_000_000  # prefers mp4+audio over webm


def test_normalize_formats_only_existing_heights() -> None:
    raw = [
        {"format_id": "1", "height": 720, "width": 1280, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 10},
        {"format_id": "2", "height": 360, "width": 640, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 5},
    ]
    formats = normalize_formats(raw)
    ids = [f.format_id for f in formats]
    # 1080 should be omitted (nothing at/above 1080); 480 snaps from nothing above 480 only if 720 exists for 720
    assert "720p" in ids
    assert "360p" in ids
    assert "audio" in ids
    assert "1080p" not in ids


def test_normalize_formats_portrait_short_side() -> None:
    """Portrait Shorts/Reels/TikTok use height=1920; short side is 1080."""
    raw = [
        {"format_id": "1", "height": 1920, "width": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 40_000_000},
        {"format_id": "2", "height": 1280, "width": 720, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "filesize": 20_000_000},
        {"format_id": "3", "height": None, "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "filesize": 2_000_000},
    ]
    formats = normalize_formats(raw)
    ids = [f.format_id for f in formats]
    assert "1080p" in ids
    assert "720p" in ids
    assert "audio" in ids
    assert formats[0].height == 1080


def test_normalize_formats_near_heights() -> None:
    """854x480 and 640x360 snap into 480p / 360p tiers."""
    raw = [
        {"format_id": "1", "height": 480, "width": 854, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 12},
        {"format_id": "2", "height": 360, "width": 640, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 6},
    ]
    formats = normalize_formats(raw)
    ids = [f.format_id for f in formats]
    assert "480p" in ids
    assert "360p" in ids
    assert "720p" not in ids
    assert "1080p" not in ids


def test_normalize_formats_float_heights() -> None:
    raw = [
        {"format_id": "1", "height": 1080.0, "width": 1920.0, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "filesize": 50},
        {"format_id": "2", "height": None, "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "filesize": 3},
    ]
    formats = normalize_formats(raw)
    ids = [f.format_id for f in formats]
    assert ids == ["1080p", "audio"]


def test_format_selector_portrait_safe() -> None:
    selector = format_selector("1080p")
    assert "height<=1080" in selector
    assert "width<=1080" in selector
    assert "bv*[width<=1080]+ba" in selector
