"""Base exception classes for the application."""

from typing import Optional


class AppException(Exception):
    """Base application exception with HTTP status code and error code."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = (
            error_code or self.__class__.__name__.replace("Error", "").upper()
        )
        self.details = details or {}
        super().__init__(message)


class ValidationError(AppException):
    """Base validation error."""

    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        self.field = field
        super().__init__(message, 422, "VALIDATION_ERROR", **kwargs)


class NotFoundError(AppException):
    """Base not found error."""

    def __init__(self, resource: str, identifier: Optional[str] = None, **kwargs):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with identifier '{identifier}' not found"
        super().__init__(message, 404, "NOT_FOUND", **kwargs)


class AlreadyExistsError(AppException):
    """Base already exists error."""

    def __init__(self, resource: str, field: str, value: str, **kwargs):
        message = f"{resource} with {field} '{value}' already exists"
        super().__init__(message, 409, "ALREADY_EXISTS", **kwargs)


class AuthenticationError(AppException):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(message, 401, "AUTHENTICATION_FAILED", **kwargs)


class AuthorizationError(AppException):
    """Authorization failed."""

    def __init__(self, message: str = "Access denied", **kwargs):
        super().__init__(message, 403, "ACCESS_DENIED", **kwargs)
