"""Unit tests for audio FFmpeg tools."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.audio import compress as compress_svc
from app.services.audio import convert as convert_svc
from app.services.audio import denoise as denoise_svc
from app.services.audio import merge as merge_svc
from app.services.audio import trim as trim_svc


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


pytestmark = pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg not on PATH")


def _tone(path: Path, seconds: float = 1.5) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-c:a",
        "pcm_s16le",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    assert proc.returncode == 0 and path.exists()
    return path


def test_convert_and_compress(tmp_path: Path) -> None:
    src = _tone(tmp_path / "tone.wav")
    mp3 = convert_svc.convert_audio(src, tmp_path / "c", "mp3", "192k")
    assert mp3.suffix == ".mp3"
    assert mp3.exists()

    flac = convert_svc.convert_audio(src, tmp_path / "f", "flac")
    assert flac.suffix == ".flac"

    compressed = compress_svc.compress_audio(src, tmp_path / "z", "small")
    assert compressed.suffix == ".mp3"
    assert compressed.exists()


def test_trim_merge_denoise(tmp_path: Path) -> None:
    a = _tone(tmp_path / "a.wav", 2.0)
    b = _tone(tmp_path / "b.wav", 1.0)

    trimmed = trim_svc.trim_audio(a, tmp_path / "t", 0.2, 1.2, mode="precise")
    assert trimmed.exists()

    merged = merge_svc.merge_audio([a, b], tmp_path / "m")
    assert merged.suffix == ".mp3"
    assert merged.exists()

    denoised = denoise_svc.denoise_audio(a, tmp_path / "d", "light")
    assert denoised.suffix == ".wav"
    assert denoised.exists()


def test_merge_requires_two(tmp_path: Path) -> None:
    a = _tone(tmp_path / "a.wav")
    with pytest.raises(AppError):
        merge_svc.merge_audio([a], tmp_path / "m")


def test_separate_skipped_without_demucs(tmp_path: Path) -> None:
    try:
        import demucs  # noqa: F401
    except ImportError:
        pytest.skip("demucs not installed")
    # Smoke: only verify import path works; full model download is too heavy for CI
    from app.services.audio import separate as separate_svc

    assert callable(separate_svc.separate_vocals)
