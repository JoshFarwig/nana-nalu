"""User domain exceptions.

All exceptions related to user operations, regardless of which layer raises them.
Can be used by repositories, services, or routes.
"""

from fastapi import status
from core.exceptions.base import NanaNaluException


# =======================
# BASE USER EXCEPTION
# =======================


class UserError(NanaNaluException):
    """Base exception for user errors"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "user_error",
        status_code: int | None = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


# =======================
# USER EXCEPTIONS
# =======================


class UserNotFoundError(UserError):
    """Raised when user doesn't exist in database"""

    def __init__(self, identifier: int | str, field: str):
        """
        Args:
            identifier: The value that was searched for (user ID, email, or username)
            field: The field that was searched ("id", "email", or "username")
        """
        super().__init__(
            message=f"User with {field} '{identifier}' not found",
            error_code="user_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"field": field, "value": str(identifier)},
        )


class UserAlreadyExistsError(UserError):
    """Raised when attempting to create user with duplicate email or username"""

    def __init__(self, field: str, value: str):
        """
        Args:
            field: The field with duplicate value ("email" or "username")
            value: The duplicate value
        """
        super().__init__(
            message=f"User with {field} '{value}' already exists",
            error_code="user_already_exists",
            status_code=status.HTTP_409_CONFLICT,
            details={"field": field, "value": value},
        )
