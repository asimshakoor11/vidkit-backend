"""Trim a video to a start–end range."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe


def trim_video(
    input_path: Path,
    output_dir: Path,
    start: float,
    end: float,
    mode: str = "fast",
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Cut [start, end). Fast = stream copy; precise = re-encode."""
    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")
    if start < 0 or end <= start or end > info.duration + 0.5:
        raise AppError(
            "INVALID_RANGE",
            "Start/end must be within the video and end must be after start.",
        )
    if mode not in {"fast", "precise"}:
        raise AppError("UNSUPPORTED_FORMAT", "Mode must be 'fast' or 'precise'.")

    clip = max(0.1, end - start)
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = input_path.suffix.lower() or ".mp4"
    out = output_dir / f"{input_path.stem}_trim{ext}"

    if mode == "fast":
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-ss",
            str(start),
            "-i",
            str(input_path),
            "-t",
            str(clip),
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            *progress_flags(),
            str(out),
        ]
    else:
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-ss",
            str(start),
            "-i",
            str(input_path),
            "-t",
            str(clip),
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            *progress_flags(),
            str(out),
        ]

    run_ffmpeg(cmd, clip, tracker, progress_callback, fail_message="Trim failed.")
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Trim produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
