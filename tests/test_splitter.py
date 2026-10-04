"""Splitter tests using a generated ffmpeg fixture (skipped if ffmpeg missing)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.ffprobe import probe, tool_version
from app.services.splitter import split_video


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and tool_version("ffmpeg") is not None


pytestmark = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")


@pytest.fixture()
def sample_video(tmp_path: Path) -> Path:
    """Generate a short test video with frequent keyframes for stream-copy splits."""
    out = tmp_path / "sample.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100",
        "-t",
        "6",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-g",
        "30",
        "-keyint_min",
        "30",
        "-force_key_frames",
        "expr:gte(t,n_forced*1)",
        "-c:a",
        "aac",
        str(out),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    assert completed.returncode == 0, completed.stderr
    assert out.exists()
    return out


def test_fast_split(sample_video: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "fast"
    parts = split_video(sample_video, out_dir, chunk_seconds=2, mode="fast")
    assert len(parts) >= 2
    info0 = probe(parts[0])
    src = probe(sample_video)
    assert info0.codec_video == src.codec_video
    assert info0.width == src.width
    assert info0.height == src.height


def test_precise_split(sample_video: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "precise"
    parts = split_video(sample_video, out_dir, chunk_seconds=2, mode="precise")
    assert len(parts) >= 2
    for part in parts:
        info = probe(part)
        assert info.duration > 0
        assert info.width == 320
        assert info.height == 240
