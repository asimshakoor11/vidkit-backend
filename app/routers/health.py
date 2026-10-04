"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.ffprobe import tool_version

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health() -> dict[str, object]:
    """Return service health plus ffmpeg / yt-dlp versions when available."""
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
    }
