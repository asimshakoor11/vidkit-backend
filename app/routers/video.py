"""Video info and download routes."""

from __future__ import annotations

import asyncio
import hashlib

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.core.security import detect_platform_from_url
from app.schemas.video import (
    JobCreatedResponse,
    VideoDownloadRequest,
    VideoInfoRequest,
    VideoInfoResponse,
)
from app.services import downloader as downloader_service
from app.services.job_service import create_job
from app.workers.runner import runner
from app.workers.tasks import run_download_job

router = APIRouter(prefix="/api/video", tags=["video"])
settings = get_settings()


def _client_id(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(host.encode()).hexdigest()[:32]


@router.post("/info", response_model=VideoInfoResponse)
@limiter.limit(settings.rate_limit_info)
async def video_info(request: Request, body: VideoInfoRequest) -> VideoInfoResponse:
    """Fetch video metadata without downloading."""
    detect_platform_from_url(body.url)
    return await asyncio.to_thread(downloader_service.extract_info, body.url)


@router.post("/download", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def video_download(
    request: Request,
    body: VideoDownloadRequest,
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    """Queue a download job for the given URL and format."""
    platform = detect_platform_from_url(body.url)
    downloader_service.format_selector(body.format_id)

    job = create_job(
        db,
        job_type="download",
        params={"url": body.url, "format_id": body.format_id},
        platform=platform,
        source_url=body.url,
        client_id=_client_id(request),
    )

    async def _factory() -> None:
        await run_download_job(job.id, body.url, body.format_id)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.get("/preview")
@limiter.limit(settings.rate_limit_info)
async def video_preview(request: Request, url: str) -> StreamingResponse:
    """Proxy a playable preview stream (supports Range for seeking)."""
    detect_platform_from_url(url)
    media_url, upstream_headers = await asyncio.to_thread(
        downloader_service.resolve_preview_media,
        url,
    )

    fwd_headers = dict(upstream_headers)
    range_header = request.headers.get("range")
    if range_header:
        fwd_headers["Range"] = range_header

    client = httpx.AsyncClient(follow_redirects=True, timeout=60.0)
    try:
        upstream = await client.send(
            client.build_request("GET", media_url, headers=fwd_headers),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise AppError("VIDEO_UNAVAILABLE", "Could not load video preview.") from exc

    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise AppError("VIDEO_UNAVAILABLE", "Could not load video preview.")

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    out_headers: dict[str, str] = {}
    for key in ("content-type", "content-length", "content-range", "accept-ranges"):
        value = upstream.headers.get(key)
        if value:
            out_headers[key] = value
    if "accept-ranges" not in out_headers:
        out_headers["accept-ranges"] = "bytes"

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers=out_headers,
        media_type=upstream.headers.get("content-type", "video/mp4"),
    )


@router.get("/thumbnail")
async def video_thumbnail(url: str) -> dict[str, str]:
    """Return thumbnail URL after validating the platform allow-list."""
    detect_platform_from_url(url)
    info = await asyncio.to_thread(downloader_service.extract_info, url)
    if not info.thumbnail_url:
        raise AppError("VIDEO_UNAVAILABLE", "No thumbnail available for this video.")
    return {"thumbnail_url": info.thumbnail_url}
