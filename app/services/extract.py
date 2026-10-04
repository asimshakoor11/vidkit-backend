"""Extract audio track from video."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe

AUDIO_FORMATS = {
    "mp3": {"ext": ".mp3", "codec": ["-c:a", "libmp3lame"], "default_bitrate": "192k"},
    "aac": {"ext": ".m4a", "codec": ["-c:a", "aac"], "default_bitrate": "192k"},
    "wav": {"ext": ".wav", "codec": ["-c:a", "pcm_s16le"], "default_bitrate": None},
}

def extract_audio(
    input_path: Path,
    output_dir: Path,
    fmt: str = "mp3",
    bitrate: str = "192k",
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Strip video and write audio-only file."""
    if fmt not in AUDIO_FORMATS:
        raise AppError("UNSUPPORTED_FORMAT", "Format must be mp3, aac, or wav.")

    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")
    if not info.codec_audio:
        raise AppError("UNSUPPORTED_FORMAT", "This file has no audio track.")

    spec = AUDIO_FORMATS[fmt]
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}{spec['ext']}"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        *spec["codec"],
    ]
    if spec["default_bitrate"] is not None:
        cmd.extend(["-b:a", bitrate or spec["default_bitrate"]])
    cmd.extend([*progress_flags(), str(out)])

    run_ffmpeg(cmd, info.duration, tracker, progress_callback, fail_message="Audio extraction failed.")
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Extraction produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
