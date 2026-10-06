"""Reduce noise in audio via FFmpeg afftdn filter."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.audio.io import DENOISE_FILTERS, out_path
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe


def denoise_audio(
    input_path: Path,
    output_dir: Path,
    preset: str = "medium",
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Apply FFmpeg afftdn noise reduction; output WAV."""
    if preset not in DENOISE_FILTERS:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be light, medium, or strong.")

    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine audio duration.")

    filt = DENOISE_FILTERS[preset]
    out = out_path(output_dir, input_path.stem, "denoised", ".wav")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-af",
        filt,
        "-c:a",
        "pcm_s16le",
        *progress_flags(),
        str(out),
    ]
    run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Noise reduction failed.")
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Denoise produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
