"""Unit tests for tool command builders / presets."""

from __future__ import annotations

from app.services.compress import CRF_PRESETS
from app.services.convert import TARGETS
from app.services.rotate import OPS
from app.services.resize import PRESETS


def test_compress_presets() -> None:
    assert CRF_PRESETS == {"high": 18, "balanced": 23, "small": 28}


def test_convert_targets() -> None:
    assert set(TARGETS) == {"mp4", "mov", "webm", "mkv", "avi"}


def test_rotate_ops() -> None:
    assert set(OPS) == {"90", "180", "270", "flip_h", "flip_v"}


def test_resize_presets() -> None:
    assert PRESETS["ig_square"] == (1080, 1080)
    assert PRESETS["yt_1080"] == (1920, 1080)
