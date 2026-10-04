"""Resize schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResizeParams(BaseModel):
    preset: str | None = Field(None, pattern="^(ig_square|ig_story|tiktok|yt_1080)$")
    width: int | None = Field(None, ge=16, le=3840)
    height: int | None = Field(None, ge=16, le=3840)
    fit: str = Field("contain", pattern="^(contain|cover)$")
