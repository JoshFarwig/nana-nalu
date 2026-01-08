from typing import Any

# NOTE: make sure to use http lib and not fastapi for
# status_code since celery workers acesses services which
# throw NanaNaluExceptions and the workers do not exist
# in a fastapi context nor do they have the package installed
from http import HTTPStatus


class NanaNaluException(Exception):
    """
    Base exception for all custom application exceptions

    All custom exceptions need to inhert from this class to
    allow for centralized logging and error handling
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.status_code = status_code or HTTPStatus.INTERNAL_SERVER_ERROR
        self.details = details or {}
        super().__init__(self.message)


class StartupError(NanaNaluException):
    """Base exception for any application startup error"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "startup",
        status_code: int | None = HTTPStatus.SERVICE_UNAVAILABLE,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, error_code, status_code, details)

    pass


class DependencyError(NanaNaluException):
    """Base exception for any dependency error"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "dependency",
        status_code: int | None = HTTPStatus.SERVICE_UNAVAILABLE,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, error_code, status_code, details)

    pass
