"""Convert schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConvertParams(BaseModel):
    target: str = Field(..., pattern="^(mp4|mov|webm|mkv|avi)$")
