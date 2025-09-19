"""Exception handlers for FastAPI application."""

from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
import logging
from typing import Annotated

from .base_exceptions import AppException
from backend.schemas.response_schema import ErrorResponse
from backend.core.dependencies.core import get_logger_dependency


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    logger = request.app.state.logger
    logger.error(f"Application error: {exc.message} [{exc.error_code}]")

    error_response = ErrorResponse(
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details if exc.details else None,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(exclude_none=True),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions."""
    logger = request.app.state.logger
    logger.warning(f"HTTP {exc.status_code}: {exc.detail}")

    error_response = ErrorResponse(
        message=exc.detail, error_code=f"HTTP_{exc.status_code}"
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(exclude_none=True),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    logger = request.app.state.logger
    logger.warning(f"Validation error: {exc.errors()}")

    error_response = ErrorResponse(
        message="Validation error",
        error_code="VALIDATION_ERROR",
        details={"errors": exc.errors()},
    )

    return JSONResponse(
        status_code=422, content=error_response.model_dump(exclude_none=True)
    )


async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    """Handle SQLAlchemy integrity constraint violations."""
    logger = request.app.state.logger
    logger.error(f"Database integrity error: {str(exc)}")

    # Parse common integrity errors
    error_msg = "Data integrity violation"
    error_str = str(exc).lower()

    if "unique constraint" in error_str or "duplicate key" in error_str:
        error_msg = "A record with this information already exists"
    elif "foreign key constraint" in error_str:
        error_msg = "Referenced record does not exist"
    elif "check constraint" in error_str:
        error_msg = "Invalid data provided"

    error_response = ErrorResponse(message=error_msg, error_code="INTEGRITY_ERROR")

    return JSONResponse(
        status_code=409, content=error_response.model_dump(exclude_none=True)
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other unhandled exceptions."""
    logger = request.app.state.logger
    logger.exception(f"Unhandled exception: {type(exc).__name__}: {str(exc)}")

    # Don't expose internal details in production
    debug_mode = (
        hasattr(request.app.state, "settings") and request.app.state.settings.debug
    )

    error_response = ErrorResponse(
        message="Internal server error",
        error_code="INTERNAL_ERROR",
        details=(
            {"exception": str(exc), "type": type(exc).__name__} if debug_mode else None
        ),
    )

    return JSONResponse(
        status_code=500, content=error_response.model_dump(exclude_none=True)
    )


def setup_exception_handlers(app):
    """Setup all exception handlers for the FastAPI app."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(Exception, general_exception_handler)
