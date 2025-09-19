"""Exception handling module exports."""

# Base exceptions
from .base_exceptions import (
    AppException,
    ValidationError,
    NotFoundError,
    AlreadyExistsError,
    AuthenticationError,
    AuthorizationError,
)

# User-specific exceptions
from .user_exceptions import (
    UserNotFoundError,
    UserAlreadyExistsError,
    InvalidCredentialsError,
    WeakPasswordError,
)

# Exception handlers
from .handlers import setup_exception_handlers

__all__ = [
    # Base exceptions
    "AppException",
    "ValidationError",
    "NotFoundError",
    "AlreadyExistsError",
    "AuthenticationError",
    "AuthorizationError",
    # User exceptions
    "UserNotFoundError",
    "UserAlreadyExistsError",
    "InvalidCredentialsError",
    "WeakPasswordError",
    # Handler setup
    "setup_exception_handlers",
]
