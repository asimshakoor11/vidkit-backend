"""Short URL model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShortUrl(Base):
    """Anonymous shortened URL redirect."""

    __tablename__ = "short_urls"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
