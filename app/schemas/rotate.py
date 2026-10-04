"""Rotate schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RotateParams(BaseModel):
    op: str = Field(..., pattern="^(90|180|270|flip_h|flip_v)$")
