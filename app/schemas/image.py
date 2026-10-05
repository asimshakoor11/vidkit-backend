"""Shared validators / constants for image tool endpoints."""

from __future__ import annotations

COMPRESS_PRESETS = {"high", "balanced", "small"}
CONVERT_FMTS = {"jpg", "jpeg", "png", "webp", "avif"}
RESIZE_MODES = {"fit", "fill", "exact"}
WATERMARK_POSITIONS = {"tl", "tr", "bl", "br", "center"}
EXIF_MODES = {"view", "strip"}
PDF_DIRECTIONS = {"to_pdf", "from_pdf"}
