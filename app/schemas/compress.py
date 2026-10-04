"""Compress schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompressParams(BaseModel):
    preset: str = Field(..., pattern="^(high|balanced|small)$")
