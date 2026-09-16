"""Centralised error types and handlers.

Every error returned by the API has the same JSON shape so the frontend can
render it consistently, and no handler leaks an internal traceback.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.logging import get_logger, request_id_var

logger = get_logger("repolens.errors")


class AppError(Exception):
    """Base class for expected, user-facing failures."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


def _serialisable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Reduce Pydantic errors to JSON-safe records.

    A custom field validator puts the raw exception object in ``ctx``, which is
    not JSON-serialisable. Rendering it directly turns every custom validation
    failure into a 500, so only the fields a client needs are kept. The input
    value is deliberately dropped: it may be a password.
    """
    errors: list[dict[str, Any]] = []
    for error in exc.errors()[:10]:
        errors.append(
            {
                "field": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
                "message": str(error.get("msg", "invalid value")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return errors


def _body(code: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "detail": detail or {},
            "request_id": request_id_var.get(),
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=_body(exc.code, exc.message, exc.detail)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", "The request payload is invalid.",
                          {"errors": _serialisable_errors(exc)}),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("database_integrity_error", error=str(exc.orig)[:300])
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_body("conflict", "The request conflicts with existing data."),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("database_error", error=str(exc)[:300])
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_body("database_unavailable", "The database is currently unavailable."),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc)[:500])
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_body("internal_error", "An unexpected error occurred."),
        )
