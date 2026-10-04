"""Resize video to social presets or custom dimensions."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe

PRESETS: dict[str, tuple[int, int]] = {
    "ig_square": (1080, 1080),
    "ig_story": (1080, 1920),
    "tiktok": (1080, 1920),
    "yt_1080": (1920, 1080),
}


def resize_video(
    input_path: Path,
    output_dir: Path,
    *,
    preset: str | None = None,
    width: int | None = None,
    height: int | None = None,
    fit: str = "contain",
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Scale/pad or crop to target size."""
    if fit not in {"contain", "cover"}:
        raise AppError("UNSUPPORTED_FORMAT", "Fit must be contain or cover.")

    if preset:
        if preset not in PRESETS:
            raise AppError("UNSUPPORTED_FORMAT", "Unknown resize preset.")
        width, height = PRESETS[preset]
    if not width or not height or width < 16 or height < 16:
        raise AppError("UNSUPPORTED_FORMAT", "Provide a preset or valid width and height.")

    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")

    if fit == "contain":
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        )
    else:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}_{width}x{height}.mp4"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-preset",
        "medium",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        *progress_flags(),
        str(out),
    ]
    run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Resize failed.")
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Resize produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
