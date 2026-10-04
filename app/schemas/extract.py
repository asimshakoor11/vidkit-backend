"""Extract-audio schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractParams(BaseModel):
    format: str = Field("mp3", pattern="^(mp3|aac|wav)$")
    bitrate: str = Field("192k", pattern="^(128k|192k|256k|320k)$")
