"""Merge schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MergeParams(BaseModel):
    file_count: int = Field(..., ge=2, le=10)
