"""User-specific exceptions."""

from typing import Optional

from .base_exceptions import NotFoundError, AlreadyExistsError, ValidationError


class UserNotFoundError(NotFoundError):
    """User not found exception."""

    def __init__(
        self,
        user_id: Optional[int] = None,
        email: Optional[str] = None,
        username: Optional[str] = None,
    ):
        if user_id:
            identifier = f"ID {user_id}"
        elif email:
            identifier = f"email '{email}'"
        elif username:
            identifier = f"username '{username}'"
        else:
            identifier = None

        super().__init__("User", identifier)


class UserAlreadyExistsError(AlreadyExistsError):
    """User already exists exception."""

    def __init__(self, field: str, value: str):
        super().__init__("User", field, value)


class InvalidCredentialsError(ValidationError):
    """Invalid login credentials."""

    def __init__(self):
        super().__init__("Invalid username/email or password")


class WeakPasswordError(ValidationError):
    """Password doesn't meet requirements."""

    def __init__(self, requirements: Optional[list] = None):
        message = "Password doesn't meet security requirements"
        details = {"requirements": requirements} if requirements else {}
        super().__init__(message, "password", details=details)
