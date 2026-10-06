"""Compress audio by re-encoding to a lower bitrate MP3."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.audio.io import COMPRESS_BITRATES, out_path
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe


def compress_audio(
    input_path: Path,
    output_dir: Path,
    preset: str = "balanced",
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Re-encode to MP3 at a preset bitrate."""
    if preset not in COMPRESS_BITRATES:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be high, balanced, or small.")

    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine audio duration.")

    bitrate = COMPRESS_BITRATES[preset]
    out = out_path(output_dir, input_path.stem, "compressed", ".mp3")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-c:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        *progress_flags(),
        str(out),
    ]
    run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Audio compression failed.")
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Compression produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
