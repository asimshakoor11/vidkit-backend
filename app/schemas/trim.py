"""Trim schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TrimParams(BaseModel):
    start: float = Field(..., ge=0)
    end: float = Field(..., gt=0)
    mode: str = Field("fast", pattern="^(fast|precise)$")
