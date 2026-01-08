from http import HTTPStatus
from core.exceptions.base import NanaNaluException


class EmailError(NanaNaluException):
    """Base exception for email errors"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "email_error",
        status_code: int | None = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


class EmailDeliveryError(EmailError):
    """Raised when email fails to send for general reasons"""

    def __init__(
        self,
        to_email: str,
        email_type: str = "email",
        reason: str | None = None,
    ):
        message = f"Failed to send {email_type} to {to_email}"
        if reason:
            message += f": {reason}"

        details = {
            "to_email": to_email,
            "email_type": email_type,
        }
        if reason:
            details["reason"] = reason

        super().__init__(
            message=message,
            error_code="email_delivery_error",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=details,
        )


class EmailServiceUnavailableError(EmailError):
    """Raised when the email provider (Resend) is unavailable (5xx errors)"""

    def __init__(
        self,
        to_email: str,
        email_type: str = "email",
        resend_status: int | None = None,
    ):
        details = {
            "to_email": to_email,
            "email_type": email_type,
        }
        message = f"Email service unavailable while sending {email_type} to {to_email}"
        if resend_status:
            message += f" (Resend returned {resend_status})"
            details["resend_status"] = str(resend_status)

        super().__init__(
            message=message,
            error_code="email_service_unavailable",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            details=details,
        )


class EmailRateLimitError(EmailError):
    """Raised when email provider per-second rate limit is exceeded (2 req/sec default)"""

    def __init__(
        self,
        to_email: str,
        email_type: str = "email",
        retry_after: int | None = None,
    ):
        message = f"Rate limit exceeded while sending {email_type} to {to_email}. "
        message += "Too many requests per second - implement queue or reduce concurrent requests"
        if retry_after:
            message += f". Retry after {retry_after} seconds"

        details = {
            "to_email": to_email,
            "email_type": email_type,
            "limit_type": "per_second",
        }
        if retry_after:
            details["retry_after"] = str(retry_after)

        super().__init__(
            message=message,
            error_code="email_rate_limit_exceeded",
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            details=details,
        )


class EmailDailyQuotaExceededError(EmailError):
    """Raised when daily email quota is exceeded"""

    def __init__(
        self,
        to_email: str,
        email_type: str = "email",
    ):
        message = (
            f"Daily email quota exceeded while sending {email_type} to {to_email}. "
            "Please try again tomorrow or upgrade your plan for increased capacity"
        )

        details = {
            "to_email": to_email,
            "email_type": email_type,
            "quota_type": "daily",
        }

        super().__init__(
            message=message,
            error_code="email_daily_quota_exceeded",
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            details=details,
        )


class EmailMonthlyQuotaExceededError(EmailError):
    """Raised when monthly email quota is exceeded"""

    def __init__(
        self,
        to_email: str,
        email_type: str = "email",
    ):
        message = (
            f"Monthly email quota exceeded while sending {email_type} to {to_email}. "
            "Please upgrade your plan or contact support to increase capacity"
        )

        details = {
            "to_email": to_email,
            "email_type": email_type,
            "quota_type": "monthly",
        }

        super().__init__(
            message=message,
            error_code="email_monthly_quota_exceeded",
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            details=details,
        )


class EmailConfigurationError(EmailError):
    """Raised when email service configuration is invalid (bad API key, invalid sender)"""

    def __init__(
        self,
        reason: str = "Invalid email service configuration",
        resend_status: int | None = None,
    ):
        message = reason
        if resend_status:
            message += f" (Resend returned {resend_status})"

        details = {}
        if resend_status:
            details["resend_status"] = str(resend_status)

        super().__init__(
            message=message,
            error_code="email_configuration_error",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=details,
        )
