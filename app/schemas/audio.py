"""Shared validators / constants for audio tool endpoints."""

from __future__ import annotations

CONVERT_FMTS = {"mp3", "wav", "aac", "flac"}
LOSSY_BITRATES = {"128k", "192k", "256k", "320k"}
COMPRESS_PRESETS = {"high", "balanced", "small"}
TRIM_MODES = {"fast", "precise"}
DENOISE_PRESETS = {"light", "medium", "strong"}
