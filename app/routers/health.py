"""Health check endpoint."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.ffprobe import tool_version

router = APIRouter(tags=["health"])


def _bin_version(configured: str, *fallbacks: str, flag: str = "--version") -> str | None:
    candidates = [configured, *fallbacks]
    for name in candidates:
        if not name:
            continue
        path = Path(name)
        exe = str(path) if path.is_file() else shutil.which(name)
        if not exe:
            continue
        try:
            proc = subprocess.run(
                [exe, flag],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            text = (proc.stdout or proc.stderr or "").strip().splitlines()
            return text[0][:120] if text else exe
        except Exception:  # noqa: BLE001
            return exe
    return None


@router.get("/api/health")
async def health() -> dict[str, object]:
    """Return service health plus tool versions when available."""
    settings = get_settings()
    ffmpeg = tool_version(settings.ffmpeg_path)
    ffprobe = tool_version(settings.ffprobe_path)
    ytdlp_version: str | None
    try:
        import yt_dlp

        ytdlp_version = getattr(yt_dlp, "version", None)
        if hasattr(ytdlp_version, "__version__"):
            ytdlp_version = ytdlp_version.__version__  # type: ignore[assignment]
        elif not isinstance(ytdlp_version, str):
            from yt_dlp.version import __version__ as yv

            ytdlp_version = yv
    except Exception:  # noqa: BLE001
        ytdlp_version = None

    return {
        "status": "ok",
        "env": settings.app_env,
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "yt_dlp": ytdlp_version,
        "ghostscript": _bin_version(settings.gs_path, "gs", "gswin64c"),
        "libreoffice": _bin_version(settings.libreoffice_path, "soffice", "libreoffice"),
        "tesseract": _bin_version(settings.tesseract_path, "tesseract"),
    }
