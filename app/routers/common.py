"""Shared helpers for tool routers."""

from __future__ import annotations

import hashlib

from fastapi import Request


def client_id(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(host.encode()).hexdigest()[:32]
