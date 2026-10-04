"""Rotate or flip a video."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe

OPS: dict[str, str] = {
    "90": "transpose=1",
    "180": "transpose=1,transpose=1",
    "270": "transpose=2",
    "flip_h": "hflip",
    "flip_v": "vflip",
}


def rotate_video(
    input_path: Path,
    output_dir: Path,
    op: str,
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Apply transpose/flip filter and re-encode to mp4."""
    if op not in OPS:
        raise AppError("UNSUPPORTED_FORMAT", "Operation must be 90, 180, 270, flip_h, or flip_v.")

    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}_rotated.mp4"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-vf",
        OPS[op],
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-preset",
        "medium",
        "-c:a",
        "copy",
        *progress_flags(),
        str(out),
    ]
    try:
        run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Rotate failed.")
    except AppError:
        # Audio copy can fail; retry with AAC
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(input_path),
            "-vf",
            OPS[op],
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
            *progress_flags(),
            str(out),
        ]
        run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Rotate failed.")

    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Rotate produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
