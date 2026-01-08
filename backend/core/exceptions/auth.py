from http import HTTPStatus
from typing import Literal
from core.exceptions.base import NanaNaluException


# =======================
# BASE AUTH EXCEPTIONS
# =======================


class AuthenticationError(NanaNaluException):
    """Base exception for authentication errors (401)"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "authentication_error",
        status_code: int | None = HTTPStatus.UNAUTHORIZED,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


class AuthorizationError(NanaNaluException):
    """Base exception for authorization errors (403)"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "authorization_error",
        status_code: int | None = HTTPStatus.FORBIDDEN,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


# =======================
# AUTHENTICATION EXCEPTIONS (401)
# =======================


class InvalidCredentialsError(AuthenticationError):
    """Raised when login credentials are incorrect"""

    def __init__(
        self,
        credential_type: Literal["email", "username"],
    ):
        # generate message based on creds
        match credential_type:
            case "email":
                message = "Invalid email or password"
            case "username":
                message = "Invalid username or password"

        details = {"identifier_type": credential_type} if credential_type else None
        super().__init__(
            message=message,
            error_code="invalid_credentials",
            status_code=HTTPStatus.UNAUTHORIZED,
            details=details,
        )


class EmailNotVerifiedError(AuthenticationError):
    """Raised when user tries to login with unverified email"""

    def __init__(self, message: str = "Email not verified"):
        super().__init__(
            message=message,
            error_code="email_not_verified",
            status_code=HTTPStatus.UNAUTHORIZED,
        )


class InvalidRefreshTokenError(AuthenticationError):
    """Raised when refresh token is invalid or expired"""

    def __init__(self, message: str = "Invalid or expired refresh token"):
        super().__init__(
            message=message,
            error_code="invalid_refresh_token",
            status_code=HTTPStatus.UNAUTHORIZED,
        )


class InvalidAccessTokenError(AuthenticationError):
    """Raised when access token is invalid or malformed"""

    def __init__(self, message: str = "Invalid or malformed access token"):
        super().__init__(
            message=message,
            error_code="invalid_access_token",
            status_code=HTTPStatus.UNAUTHORIZED,
        )


class TokenExpiredError(AuthenticationError):
    """Raised when a token has expired"""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(
            message=message,
            error_code="token_expired",
            status_code=HTTPStatus.UNAUTHORIZED,
        )


# =======================
# AUTHORIZATION EXCEPTIONS (403)
# =======================


class InsufficientPermissionsError(AuthorizationError):
    """Raised when user lacks required permissions"""

    def __init__(
        self,
        message: str = "Insufficient permissions for this action",
        details: dict | None = None,
    ):
        super().__init__(
            message=message,
            error_code="insufficient_permissions",
            status_code=HTTPStatus.FORBIDDEN,
            details=details,
        )


class AccountDisabledError(AuthorizationError):
    """Raised when attempting to authenticate with disabled account"""

    def __init__(
        self, message: str = "Account has been disabled", details: dict | None = None
    ):
        super().__init__(
            message=message,
            error_code="account_disabled",
            status_code=HTTPStatus.FORBIDDEN,
            details=details,
        )
