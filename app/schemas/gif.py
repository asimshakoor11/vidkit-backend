"""GIF schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GifParams(BaseModel):
    start: float = Field(0, ge=0)
    duration: float = Field(5, gt=0, le=60)
    width: int = Field(480, ge=64, le=1920)
    fps: int = Field(10, ge=8, le=15)
