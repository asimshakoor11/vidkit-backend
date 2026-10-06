"""Convert audio between formats via FFmpeg."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.audio.io import format_spec, out_path
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe


def convert_audio(
    input_path: Path,
    output_dir: Path,
    fmt: str = "mp3",
    bitrate: str = "192k",
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Re-encode audio to the target format."""
    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine audio duration.")

    spec = format_spec(fmt)
    out = out_path(output_dir, input_path.stem, "converted", spec["ext"])
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        *spec["codec"],
    ]
    if spec["lossy"]:
        cmd.extend(["-b:a", bitrate or "192k"])
    cmd.extend([*progress_flags(), str(out)])

    run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Audio conversion failed.")
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Conversion produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
