"""Video compression via libx264 CRF presets."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe

CRF_PRESETS = {
    "high": 18,
    "balanced": 23,
    "small": 28,
}


def compress_video(
    input_path: Path,
    output_dir: Path,
    preset: str,
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Re-encode with libx264; keep resolution/fps; AAC audio."""
    if preset not in CRF_PRESETS:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be high, balanced, or small.")

    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}_compressed.mp4"
    crf = CRF_PRESETS[preset]
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-preset",
        "medium",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        *progress_flags(),
        str(out),
    ]
    run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Compression failed.")
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Compression produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
