"""Application error types and FastAPI exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Domain error mapped to the standard API error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    """Build the standard error response body."""
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = "INTERNAL_ERROR" if exc.status_code >= 500 else "INVALID_URL"
        if exc.status_code == 404:
            code = "JOB_NOT_FOUND"
        elif exc.status_code == 429:
            code = "RATE_LIMITED"
        message = str(exc.detail) if exc.detail else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, message),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        message = "Invalid request"
        if exc.errors():
            first = exc.errors()[0]
            loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
            msg = first.get("msg", message)
            message = f"{loc}: {msg}" if loc else str(msg)
        return JSONResponse(
            status_code=422,
            content=error_body("INVALID_URL", message),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_body("INTERNAL_ERROR", "An unexpected error occurred"),
        )
