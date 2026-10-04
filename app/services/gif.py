"""Make an animated GIF from a video clip."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe


def make_gif(
    input_path: Path,
    output_dir: Path,
    start: float = 0.0,
    duration: float = 5.0,
    width: int = 480,
    fps: int = 10,
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Export a palette-optimized GIF for the selected clip."""
    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")
    if start < 0 or duration <= 0 or start >= info.duration:
        raise AppError("INVALID_RANGE", "Invalid start time or duration for GIF.")
    if width < 64 or width > 1920:
        raise AppError("UNSUPPORTED_FORMAT", "Width must be between 64 and 1920.")
    if fps < 8 or fps > 15:
        raise AppError("UNSUPPORTED_FORMAT", "FPS must be between 8 and 15.")

    clip = min(duration, info.duration - start)
    output_dir.mkdir(parents=True, exist_ok=True)
    palette = output_dir / "palette.png"
    out = output_dir / f"{input_path.stem}.gif"

    # Two-pass palette for quality
    pass1 = [
        ffmpeg_bin(),
        "-y",
        "-ss",
        str(start),
        "-t",
        str(clip),
        "-i",
        str(input_path),
        "-vf",
        f"fps={fps},scale={width}:-1:flags=lanczos,palettegen",
        *progress_flags(),
        str(palette),
    ]
    run_ffmpeg(pass1, clip, tracker, progress_callback, stage="processing", fail_message="GIF palette failed.")

    pass2 = [
        ffmpeg_bin(),
        "-y",
        "-ss",
        str(start),
        "-t",
        str(clip),
        "-i",
        str(input_path),
        "-i",
        str(palette),
        "-lavfi",
        f"fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse",
        *progress_flags(),
        str(out),
    ]
    run_ffmpeg(pass2, clip, tracker, progress_callback, stage="processing", fail_message="GIF creation failed.")
    palette.unlink(missing_ok=True)

    if not out.exists():
        raise AppError("INTERNAL_ERROR", "GIF produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
