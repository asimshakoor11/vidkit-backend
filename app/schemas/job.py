"""Job status schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobOutputOut(BaseModel):
    """A single downloadable job output."""

    file_id: str
    name: str
    part_index: int | None = None
    duration_seconds: float | None = None
    size_bytes: int
    download_url: str


class JobStatusResponse(BaseModel):
    """Job polling response."""

    job_id: str
    type: str
    status: str
    stage: str | None = None
    progress: int
    error: str | None = None
    created_at: datetime
    expires_at: datetime
    outputs: list[JobOutputOut] = []
    zip_url: str | None = None
