"""
middleware/error_handler.py
===========================
Global exception handlers that translate all unhandled exceptions into a
standardised ``StructuralAPIError`` JSON response.

The frontend and agent orchestration layer must **never** receive a raw Python
traceback or an unstructured 500 response.

Error response shape
--------------------
All errors return::

    {
        "error_code": "ANALYSIS_FAILED",
        "message": "Analysis engine returned an error for one or more members.",
        "member_id": "B-14",          # optional
        "stage": "analysis",          # optional
        "details": { ... }            # optional extended context
    }

Usage
-----
Call ``register_error_handlers(app)`` in ``main.py`` after creating the
``FastAPI`` instance.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import ERROR_CODES

logger = logging.getLogger(__name__)


# ─── Response model ───────────────────────────────────────────────────────────


class StructuralAPIError(BaseModel):
    """
    Standardised error envelope returned by all error handlers.

    Attributes
    ----------
    error_code : str
        Machine-readable error code from the registry in ``config.py``.
    message : str
        Human-readable explanation of the error.
    member_id : str | None
        Affected member identifier, when applicable.
    stage : str | None
        Pipeline stage in which the error occurred.
    details : dict | None
        Extended context (validation field errors, raw exception message, etc.).
    """

    error_code: str
    message: str
    member_id: Optional[str] = None
    stage: Optional[str] = None
    details: Optional[dict[str, Any]] = None


# ─── Custom exception ─────────────────────────────────────────────────────────


class StructuralError(Exception):
    """
    Domain-specific exception raised by service layer code.

    Raise this instead of ``HTTPException`` inside service methods so that
    the error handler can attach the full ``StructuralAPIError`` envelope.

    Parameters
    ----------
    error_code : str
        Key from ``config.ERROR_CODES``.
    member_id : str | None
        Affected member identifier.
    stage : str | None
        Pipeline stage where the error originated.
    details : dict | None
        Extra context.
    status_code : int
        HTTP status to return (default 422).
    """

    def __init__(
        self,
        error_code: str,
        member_id: Optional[str] = None,
        stage: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY,
    ) -> None:
        self.error_code = error_code
        self.message = ERROR_CODES.get(error_code, error_code)
        self.member_id = member_id
        self.stage = stage
        self.details = details
        self.status_code = status_code
        super().__init__(self.message)


# ─── Handlers ─────────────────────────────────────────────────────────────────


def _make_error_response(
    error_code: str,
    message: str,
    status_code: int,
    member_id: Optional[str] = None,
    stage: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    """Build a ``JSONResponse`` with the ``StructuralAPIError`` envelope."""
    body = StructuralAPIError(
        error_code=error_code,
        message=message,
        member_id=member_id,
        stage=stage,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def register_error_handlers(app: FastAPI) -> None:
    """
    Attach all global exception handlers to a FastAPI application instance.

    Parameters
    ----------
    app : FastAPI
        The application to register handlers on.
    """

    @app.exception_handler(StructuralError)
    async def structural_error_handler(request: Request, exc: StructuralError) -> JSONResponse:
        """Handle domain-specific StructuralError exceptions."""
        logger.warning(
            "StructuralError [%s] on %s %s — %s",
            exc.error_code,
            request.method,
            request.url.path,
            exc.message,
        )
        return _make_error_response(
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            member_id=exc.member_id,
            stage=exc.stage,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic request validation errors (422)."""
        field_errors = []
        for err in exc.errors():
            field_errors.append(
                {
                    "field": " → ".join(str(loc) for loc in err["loc"]),
                    "issue": err["msg"],
                    "type": err["type"],
                }
            )
        logger.info(
            "Validation error on %s %s — %d field error(s)",
            request.method,
            request.url.path,
            len(field_errors),
        )
        return _make_error_response(
            error_code="INVALID_LOAD_INPUT",
            message="Request body failed schema validation.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"field_errors": field_errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler for unexpected exceptions — prevents raw tracebacks leaking."""
        logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
        )
        details: dict[str, Any] = {"exception_type": type(exc).__name__}
        from config import settings

        if settings.APP_ENV != "production":
            details["traceback"] = traceback.format_exc()
        return _make_error_response(
            error_code="ANALYSIS_FAILED",
            message=f"An unexpected server error occurred: {exc}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )
