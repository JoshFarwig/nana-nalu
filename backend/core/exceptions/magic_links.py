from http import HTTPStatus

from core.exceptions.base import NanaNaluException


# =======================
# BASE MAGIC LINK EXCEPTION
# =======================


class MagicLinkError(NanaNaluException):
    """Base exception for magic link errors"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "magic_link_error",
        status_code: int | None = HTTPStatus.BAD_REQUEST,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


# =======================
# VALIDATION EXCEPTIONS
# =======================


class MagicLinkInvalidError(MagicLinkError):
    """
    Raised when magic link token is invalid.

    This covers multiple scenarios that are indistinguishable with Redis TTL:
    - Token never existed
    - Token expired (TTL elapsed)
    - Token already consumed (GETDEL removed it)
    - Wrong token type (key doesn't exist for expected type)

    We intentionally don't distinguish these to avoid leaking information
    about token existence to potential attackers.
    """

    def __init__(self, message: str = "This link is invalid or has expired"):
        super().__init__(
            message=message,
            error_code="magic_link_invalid",
            status_code=HTTPStatus.BAD_REQUEST,
        )


# =======================
# RATE LIMITING
# =======================


class MagicLinkRateLimitError(MagicLinkError):
    """
    Raised when user requests too many magic links.

    Prevents spam/abuse of email verification or password reset.
    """

    def __init__(
        self,
        message: str = "Too many requests. Please wait before requesting another link.",
        retry_after_seconds: int | None = None,
    ):
        details = {"retry_after": retry_after_seconds} if retry_after_seconds else None
        super().__init__(
            message=message,
            error_code="magic_link_rate_limit",
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            details=details,
        )
