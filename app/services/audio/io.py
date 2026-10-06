"""Shared helpers for audio FFmpeg tools."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError

AUDIO_FORMATS = {
    "mp3": {"ext": ".mp3", "codec": ["-c:a", "libmp3lame"], "lossy": True},
    "aac": {"ext": ".m4a", "codec": ["-c:a", "aac"], "lossy": True},
    "wav": {"ext": ".wav", "codec": ["-c:a", "pcm_s16le"], "lossy": False},
    "flac": {"ext": ".flac", "codec": ["-c:a", "flac"], "lossy": False},
}

COMPRESS_BITRATES = {
    "high": "256k",
    "balanced": "128k",
    "small": "64k",
}

DENOISE_FILTERS = {
    "light": "afftdn=nr=6:nf=-25",
    "medium": "afftdn=nr=12:nf=-20",
    "strong": "afftdn=nr=20:nf=-15",
}


def format_spec(fmt: str) -> dict:
    if fmt not in AUDIO_FORMATS:
        raise AppError("UNSUPPORTED_FORMAT", "Format must be mp3, wav, aac, or flac.")
    return AUDIO_FORMATS[fmt]


def out_path(output_dir: Path, stem: str, suffix: str, ext: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem)[:80] or "audio"
    return output_dir / f"{safe}_{suffix}{ext}"
