"""Convert video between common containers."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe

# target -> (ext, video_args, audio_args)
TARGETS: dict[str, tuple[str, list[str], list[str]]] = {
    "mp4": (".mp4", ["-c:v", "libx264", "-crf", "23", "-preset", "medium"], ["-c:a", "aac", "-b:a", "192k"]),
    "mov": (".mov", ["-c:v", "libx264", "-crf", "23", "-preset", "medium"], ["-c:a", "aac", "-b:a", "192k"]),
    "webm": (".webm", ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0"], ["-c:a", "libopus", "-b:a", "128k"]),
    "mkv": (".mkv", ["-c:v", "libx264", "-crf", "23", "-preset", "medium"], ["-c:a", "aac", "-b:a", "192k"]),
    "avi": (".avi", ["-c:v", "libx264", "-crf", "23", "-preset", "medium"], ["-c:a", "aac", "-b:a", "192k"]),
}


def convert_video(
    input_path: Path,
    output_dir: Path,
    target: str,
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Convert to the requested container/codec pair."""
    if target not in TARGETS:
        raise AppError("UNSUPPORTED_FORMAT", "Target must be mp4, mov, webm, mkv, or avi.")

    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")

    ext, vargs, aargs = TARGETS[target]
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}{ext}"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        *vargs,
        *aargs,
        *progress_flags(),
        str(out),
    ]
    run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Conversion failed.")
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Conversion produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
