import logging
from fastapi import status
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from core.exceptions.base import NanaNaluException

logger = logging.getLogger(__name__)


def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Exception handler used for any uncaught exceptions"""

    logger.critical(
        f"Unhandled Exception: {exc.__class__.__name__}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method,
        },
    )

    response_body = {
        "message": "An unexpected error occured",
        "error_code": "internal_server_error",
        "details": None,
    }

    return JSONResponse(
        content=response_body, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Exception handler used for any request validation errors"""

    logger.warning(
        f"Validation error on {request.method} {request.url.path}",
        extra={"errors": exc.errors()},
    )
    errors = [
        {
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]

    response_body = {
        "message": "Validation error",
        "error_code": "validation_error",
        "details": {"errors": errors},
    }

    return JSONResponse(
        content=response_body, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )


def nana_nalu_exception_handler(
    request: Request, exc: NanaNaluException
) -> JSONResponse:
    """Exception handler used for NanaNaluExceptions"""

    status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    log_level = (
        logging.WARNING
        if status_code < status.HTTP_500_INTERNAL_SERVER_ERROR
        else logging.ERROR
    )

    log_message = f"{exc.__class__.__name__}: {exc.message}"
    logger.log(
        log_level,
        log_message,
        exc_info=status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR,
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_class": exc.__class__.__name__,
            "error_code": exc.error_code,
            "status_code": exc.status_code,
        },
    )

    response_body = {
        "message": exc.message,
        "error_code": exc.error_code,
        "details": exc.details,
    }

    return JSONResponse(content=response_body, status_code=status_code)
