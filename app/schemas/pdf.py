"""Shared validators / constants for PDF tool endpoints."""

from __future__ import annotations

COMPRESS_PRESETS = {"screen", "ebook", "printer"}
SPLIT_MODES = {"each", "ranges"}
ROTATE_ANGLES = {"90", "180", "270"}
WATERMARK_POSITIONS = {"tl", "tr", "bl", "br", "center"}
PAGE_NUM_POSITIONS = {"bl", "bc", "br", "tl", "tc", "tr"}
ESIGN_POSITIONS = {"bl", "br", "bc", "tl", "tr", "center"}
OCR_LANGS = {"eng", "spa", "fra", "deu", "ita", "por", "nld", "pol", "tur", "rus", "chi_sim", "jpn"}
JPG_DPIS = {72, 100, 150, 200, 300}
