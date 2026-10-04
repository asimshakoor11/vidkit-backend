"""Video info and download schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VideoInfoRequest(BaseModel):
    """Request body for POST /api/video/info."""

    url: str = Field(..., min_length=1)


class VideoFormatOut(BaseModel):
    """Normalized downloadable format option."""

    format_id: str
    label: str
    kind: str
    ext: str
    height: int | None = None
    filesize_bytes: int | None = None
    estimated: bool = True


class VideoInfoResponse(BaseModel):
    """Metadata response for a video URL."""

    platform: str
    title: str
    uploader: str
    duration_seconds: int
    thumbnail_url: str | None = None
    embed_url: str | None = None
    formats: list[VideoFormatOut]


class VideoDownloadRequest(BaseModel):
    """Request body for POST /api/video/download."""

    url: str = Field(..., min_length=1)
    format_id: str = Field(..., min_length=1)


class JobCreatedResponse(BaseModel):
    """Accepted response when a job is queued."""

    job_id: str
    status: str = "queued"
