"""ffprobe helpers for media metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProbeInfo:
    """Normalized probe result for a media file."""

    duration: float
    width: int | None
    height: int | None
    fps: float | None
    codec_video: str | None
    codec_audio: str | None
    rotation: int
    raw: dict[str, Any]


def _run_ffprobe(path: Path) -> dict[str, Any]:
    settings = get_settings()
    binary = settings.ffprobe_path
    if shutil.which(binary) is None and binary == "ffprobe":
        raise AppError(
            "INTERNAL_ERROR",
            "ffprobe is not installed or not on PATH.",
            status_code=500,
        )
    cmd = [
        binary,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise AppError(
            "INTERNAL_ERROR",
            "ffprobe is not installed or not on PATH.",
            status_code=500,
        ) from exc

    if completed.returncode != 0:
        logger.error("ffprobe_failed", stderr=completed.stderr)
        raise AppError("UNSUPPORTED_FORMAT", "Could not read this video file.")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AppError("UNSUPPORTED_FORMAT", "Could not read this video file.") from exc


def _parse_fps(rate: str | None) -> float | None:
    if not rate or rate in {"0/0", "N/A"}:
        return None
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            den_f = float(den)
            if den_f == 0:
                return None
            return float(num) / den_f
        except ValueError:
            return None
    try:
        return float(rate)
    except ValueError:
        return None


def _rotation_from_stream(stream: dict[str, Any]) -> int:
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        try:
            return int(float(tags["rotate"])) % 360
        except ValueError:
            pass
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            try:
                return int(float(side["rotation"])) % 360
            except ValueError:
                continue
    return 0


def probe(path: Path) -> ProbeInfo:
    """Probe a media file and return normalized metadata."""
    data = _run_ffprobe(path)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format") or {}

    duration = 0.0
    if fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
        except ValueError:
            duration = 0.0
    if duration <= 0 and video and video.get("duration"):
        try:
            duration = float(video["duration"])
        except ValueError:
            duration = 0.0

    return ProbeInfo(
        duration=duration,
        width=int(video["width"]) if video and video.get("width") else None,
        height=int(video["height"]) if video and video.get("height") else None,
        fps=_parse_fps(video.get("avg_frame_rate") if video else None),
        codec_video=video.get("codec_name") if video else None,
        codec_audio=audio.get("codec_name") if audio else None,
        rotation=_rotation_from_stream(video) if video else 0,
        raw=data,
    )


def tool_version(binary: str) -> str | None:
    """Return the first line of `binary -version`, or None if unavailable."""
    try:
        completed = subprocess.run(
            [binary, "-version"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    line = (completed.stdout or completed.stderr or "").splitlines()
    return line[0] if line else None
