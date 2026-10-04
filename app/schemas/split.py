"""Split job schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SplitJobParams(BaseModel):
    """Validated split parameters."""

    chunk_seconds: int = Field(..., ge=1)
    mode: str = Field(..., pattern="^(fast|precise)$")


class SplitFromUrlRequest(BaseModel):
    """Request body for POST /api/split/from-url."""

    url: str = Field(..., min_length=1)
    format_id: str = Field(..., min_length=1)
    chunk_seconds: int = Field(..., ge=1)
    mode: str = Field(..., pattern="^(fast|precise)$")
