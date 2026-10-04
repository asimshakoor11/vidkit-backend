"""yt-dlp wrapper for metadata extraction and downloads."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.utils import DownloadError

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.schemas.video import VideoFormatOut, VideoInfoResponse
from app.services.platform_detector import detect_platform

logger = get_logger(__name__)

TARGET_HEIGHTS = (1080, 720, 480, 360)


def _base_opts() -> dict[str, Any]:
    settings = get_settings()
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 15,
    }
    if settings.ytdlp_cookies_file:
        opts["cookiefile"] = settings.ytdlp_cookies_file
    return opts


def map_ytdlp_error(exc: Exception) -> AppError:
    """Map yt-dlp exceptions to AppError codes."""
    message = str(exc).lower()
    if "private" in message or "login required" in message or "sign in" in message:
        return AppError(
            "PRIVATE_OR_LOGIN_REQUIRED",
            "This video is private or requires login.",
            status_code=403,
        )
    if "geo" in message or "not available in your country" in message:
        return AppError("GEO_BLOCKED", "This video is not available in your region.", status_code=403)
    if "unsupported url" in message or "no suitable" in message:
        return AppError("UNSUPPORTED_PLATFORM", "Unsupported or invalid video URL.")
    if "unavailable" in message or "does not exist" in message or "404" in message:
        return AppError("VIDEO_UNAVAILABLE", "This video is unavailable.")
    return AppError("VIDEO_UNAVAILABLE", "Could not fetch video information.")


def _youtube_embed_url(url: str, info: dict[str, Any]) -> str | None:
    video_id = info.get("id")
    if not video_id:
        parsed = urlparse(url)
        if "youtu.be" in (parsed.hostname or ""):
            video_id = parsed.path.strip("/")
        else:
            video_id = parse_qs(parsed.query).get("v", [None])[0]
    if video_id:
        return f"https://www.youtube.com/embed/{video_id}"
    return None


def _parse_duration_string(value: str) -> int | None:
    parts = value.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 1 and nums[0] > 0:
        return nums[0]
    return None


def _coerce_duration_seconds(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = int(value)
        return seconds if seconds > 0 else None
    if isinstance(value, str) and value.strip():
        return _parse_duration_string(value)
    return None


def extract_duration(info: dict[str, Any]) -> int:
    """Best-effort duration; Instagram often omits top-level duration."""
    for key in ("duration", "video_duration", "approx_duration"):
        seconds = _coerce_duration_seconds(info.get(key))
        if seconds:
            return seconds

    approx_ms = info.get("approx_duration_ms") or info.get("duration_ms")
    if isinstance(approx_ms, (int, float)) and approx_ms > 0:
        return max(1, int(approx_ms / 1000))

    ds = info.get("duration_string")
    if isinstance(ds, str):
        parsed = _parse_duration_string(ds)
        if parsed:
            return parsed

    for fmt in info.get("formats") or []:
        seconds = _coerce_duration_seconds(fmt.get("duration"))
        if seconds:
            return seconds

    return 0


def _pick_filesize(fmt: dict[str, Any]) -> tuple[int | None, bool]:
    for key in ("filesize", "filesize_approx"):
        value = fmt.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value), key == "filesize_approx"
    return None, True


def _coerce_dimension(value: Any) -> int | None:
    """Coerce yt-dlp width/height (int or float) to a positive int."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        dim = int(value)
        return dim if dim > 0 else None
    return None


def _ladder_quality(fmt: dict[str, Any]) -> int | None:
    """Short-side resolution so portrait 1080x1920 maps to 1080, not 1920."""
    height = _coerce_dimension(fmt.get("height"))
    width = _coerce_dimension(fmt.get("width"))
    if height and width:
        return min(height, width)
    return height or width


def _snap_to_target(quality: int) -> int | None:
    """Map a ladder quality to the highest target tier it satisfies."""
    for target in TARGET_HEIGHTS:
        if quality >= target:
            return target
    return None


def normalize_formats(raw_formats: list[dict[str, Any]] | None) -> list[VideoFormatOut]:
    """Collapse yt-dlp formats into a clean 1080/720/480/360 + audio list."""
    formats = raw_formats or []
    by_target: dict[int, dict[str, Any]] = {}

    for fmt in formats:
        vcodec = fmt.get("vcodec") or "none"
        acodec = fmt.get("acodec") or "none"
        if vcodec == "none":
            continue
        quality = _ladder_quality(fmt)
        if quality is None:
            continue
        target = _snap_to_target(quality)
        if target is None:
            continue
        # Prefer mp4 / h264-ish progressive or video-only; prefer higher source quality in-tier
        ext = (fmt.get("ext") or "").lower()
        score = quality  # higher ladder quality wins within the same tier
        if ext == "mp4":
            score += 10_000
        if acodec != "none":
            score += 5_000
        if "avc" in vcodec or "h264" in vcodec:
            score += 3_000
        existing = by_target.get(target)
        existing_score = existing.get("_score", -1) if existing else -1
        if score >= existing_score:
            entry = dict(fmt)
            entry["_score"] = score
            by_target[target] = entry

    result: list[VideoFormatOut] = []
    for target in TARGET_HEIGHTS:
        if target not in by_target:
            continue
        fmt = by_target[target]
        size, estimated = _pick_filesize(fmt)
        result.append(
            VideoFormatOut(
                format_id=f"{target}p",
                label=f"{target}p MP4",
                kind="video",
                ext="mp4",
                height=target,
                filesize_bytes=size,
                estimated=estimated or size is None,
            )
        )

    # Audio-only option when any audio stream exists
    has_audio = any(
        (f.get("acodec") or "none") != "none" for f in formats
    ) or any((f.get("vcodec") or "none") != "none" for f in formats)
    if has_audio:
        audio_candidates = [
            f
            for f in formats
            if (f.get("acodec") or "none") != "none" and (f.get("vcodec") or "none") == "none"
        ]
        size = None
        estimated = True
        if audio_candidates:
            size, estimated = _pick_filesize(audio_candidates[0])
        result.append(
            VideoFormatOut(
                format_id="audio",
                label="Audio only MP3",
                kind="audio",
                ext="mp3",
                height=None,
                filesize_bytes=size,
                estimated=estimated or size is None,
            )
        )

    return result


def extract_info(url: str) -> VideoInfoResponse:
    """Fetch metadata for a URL without downloading media."""
    platform = detect_platform(url)
    opts = _base_opts()
    opts["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise map_ytdlp_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("extract_info_failed", url=url)
        raise map_ytdlp_error(exc) from exc

    if not info:
        raise AppError("VIDEO_UNAVAILABLE", "This video is unavailable.")

    # Flatten playlists to first entry if needed
    if info.get("_type") == "playlist" and info.get("entries"):
        info = next((e for e in info["entries"] if e), None) or info

    duration = extract_duration(info)
    formats = normalize_formats(info.get("formats"))
    embed_url = _youtube_embed_url(url, info) if platform == "youtube" else None

    return VideoInfoResponse(
        platform=platform,
        title=str(info.get("title") or "Untitled"),
        uploader=str(info.get("uploader") or info.get("channel") or "Unknown"),
        duration_seconds=duration,
        thumbnail_url=info.get("thumbnail"),
        embed_url=embed_url,
        formats=formats,
    )


def resolve_preview_media(url: str) -> tuple[str, dict[str, str]]:
    """Resolve a progressive media URL + headers for in-browser preview streaming."""
    detect_platform(url)
    opts = _base_opts()
    opts.update(
        {
            "skip_download": True,
            # Prefer a single progressive file the browser can play without remux
            "format": "b[ext=mp4]/best[ext=mp4]/bv*[ext=mp4]+ba/b/best",
        }
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise map_ytdlp_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("resolve_preview_failed", url=url)
        raise map_ytdlp_error(exc) from exc

    if not info:
        raise AppError("VIDEO_UNAVAILABLE", "This video is unavailable.")

    if info.get("_type") == "playlist" and info.get("entries"):
        info = next((e for e in info["entries"] if e), None) or info

    headers: dict[str, str] = {}
    raw_headers = info.get("http_headers") or {}
    if isinstance(raw_headers, dict):
        headers = {str(k): str(v) for k, v in raw_headers.items()}

    direct = info.get("url")
    if isinstance(direct, str) and direct.startswith("http"):
        return direct, headers

    # Prefer progressive (has both video+audio) then any video stream with a URL
    candidates: list[dict[str, Any]] = [
        f for f in (info.get("formats") or []) if isinstance(f.get("url"), str)
    ]
    progressive = [
        f
        for f in candidates
        if (f.get("vcodec") or "none") != "none" and (f.get("acodec") or "none") != "none"
    ]
    video_only = [f for f in candidates if (f.get("vcodec") or "none") != "none"]
    for group in (progressive, video_only, candidates):
        if group:
            # highest quality-ish last entries often better; pick last with mp4 preference
            mp4 = [f for f in group if (f.get("ext") or "").lower() == "mp4"]
            chosen = (mp4 or group)[-1]
            fmt_headers = chosen.get("http_headers") or {}
            if isinstance(fmt_headers, dict) and fmt_headers:
                headers = {str(k): str(v) for k, v in fmt_headers.items()}
            return str(chosen["url"]), headers

    raise AppError("VIDEO_UNAVAILABLE", "No playable preview stream found for this video.")


def format_selector(format_id: str) -> str:
    """Build a yt-dlp format selector from a normalized format_id.

    Supports landscape and portrait: either dimension may be the ladder side.
    """
    if format_id == "audio":
        return "bestaudio/best"
    match = re.fullmatch(r"(\d+)p", format_id)
    if not match:
        raise AppError("UNSUPPORTED_FORMAT", f"Unknown format: {format_id}")
    h = int(match.group(1))
    return (
        f"bv*[height<={h}][width<={h}]+ba/"
        f"bv*[height<={h}]+ba/"
        f"bv*[width<={h}]+ba/"
        f"b[height<={h}]/"
        f"b[width<={h}]/"
        f"best"
    )


def download_video(
    url: str,
    format_id: str,
    output_dir: Path,
    progress_callback: Callable[[float, str], None] | None = None,
) -> Path:
    """
    Download a video into output_dir and return the final file path.

    Runs synchronously; callers should offload to a thread.
    """
    detect_platform(url)
    output_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(output_dir / "%(title).80B [%(id)s].%(ext)s")

    opts = _base_opts()
    opts.update(
        {
            "format": format_selector(format_id),
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "retries": 3,
        }
    )

    if format_id == "audio":
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    last_update = 0.0

    def hook(data: dict[str, Any]) -> None:
        nonlocal last_update
        if not progress_callback:
            return
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percent = (downloaded / total * 90.0) if total else 5.0
            if percent - last_update >= 1.0:
                last_update = percent
                progress_callback(min(percent, 90.0), "downloading")
        elif status == "finished":
            progress_callback(95.0, "merging")

    opts["progress_hooks"] = [hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if format_id == "audio":
                # After postprocessor, locate mp3
                prepared = ydl.prepare_filename(info)
                mp3_path = Path(prepared).with_suffix(".mp3")
                if mp3_path.exists():
                    return mp3_path
            filename = ydl.prepare_filename(info)
            # merge may change extension to mp4
            path = Path(filename)
            if not path.exists():
                mp4 = path.with_suffix(".mp4")
                if mp4.exists():
                    return mp4
            if path.exists():
                return path
            # Fallback: newest file in directory
            files = sorted(output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                return files[0]
            raise AppError("INTERNAL_ERROR", "Download finished but file was not found.")
    except AppError:
        raise
    except DownloadError as exc:
        raise map_ytdlp_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("download_failed", url=url)
        raise map_ytdlp_error(exc) from exc
