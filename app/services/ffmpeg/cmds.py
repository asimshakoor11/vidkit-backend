"""Shared FFmpeg helpers (bin path, progress flags)."""

from __future__ import annotations

import shutil

from app.core.config import get_settings
from app.core.errors import AppError


def ffmpeg_bin() -> str:
    """Resolve ffmpeg binary from settings / PATH."""
    settings = get_settings()
    binary = settings.ffmpeg_path
    if shutil.which(binary) is None and binary == "ffmpeg":
        raise AppError(
            "INTERNAL_ERROR",
            "ffmpeg is not installed or not on PATH.",
            status_code=500,
        )
    return binary


def progress_flags() -> list[str]:
    """Common flags so run_ffmpeg can parse -progress pipe:1."""
    return ["-progress", "pipe:1", "-nostats"]
