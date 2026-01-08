import logging
from httpx import HTTPStatusError, HTTPError
from pydantic import EmailStr

from core.config import APISettings
from core.templates import TemplateRenderer
from core.http import AsyncHTTPManager
from core.exceptions.emails import (
    EmailDeliveryError,
    EmailServiceUnavailableError,
    EmailRateLimitError,
    EmailDailyQuotaExceededError,
    EmailMonthlyQuotaExceededError,
    EmailConfigurationError,
)

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(
        self,
        http_manager: AsyncHTTPManager,
        template_renderer: TemplateRenderer,
        settings: APISettings,
    ) -> None:
        self.http_manager = http_manager
        self.template_renderer = template_renderer
        self.settings = settings.api

    def _handle_http_status_error(
        self, error: HTTPStatusError, to_email: str, email_type: str
    ):
        """Parse Resend API errors and raise appropriate domain exceptions"""
        status_code = error.response.status_code

        # rate limiting and quota errors (429)
        if status_code == 429:
            # parse error code from response body
            try:
                error_body = error.response.json()
                error_code = error_body.get("name", "")
            except Exception:
                error_code = ""

            retry_after = error.response.headers.get("Retry-After")
            retry_after_int = int(retry_after) if retry_after else None

            # check specific quota/rate limit type
            if error_code == "daily_quota_exceeded":
                raise EmailDailyQuotaExceededError(
                    to_email=to_email,
                    email_type=email_type,
                ) from error
            elif error_code == "monthly_quota_exceeded":
                raise EmailMonthlyQuotaExceededError(
                    to_email=to_email,
                    email_type=email_type,
                ) from error
            else:
                # default to per-second rate limit
                raise EmailRateLimitError(
                    to_email=to_email,
                    email_type=email_type,
                    retry_after=retry_after_int,
                ) from error

        # configuration errors (unauthorized, forbidden)
        elif status_code in (401, 403):
            raise EmailConfigurationError(
                reason="Invalid API key or insufficient permissions",
                resend_status=status_code,
            ) from error

        # service unavailable (5xx errors)
        elif status_code >= 500:
            raise EmailServiceUnavailableError(
                to_email=to_email,
                email_type=email_type,
                resend_status=status_code,
            ) from error

        # other client errors (4xx)
        else:
            raise EmailDeliveryError(
                to_email=to_email,
                email_type=email_type,
                reason=f"Resend returned {status_code}",
            ) from error

    async def _send_email(
        self,
        to_email: EmailStr,
        subject: str,
        html_body: str,
        email_type: str,
        username: str,
    ):
        """
        Centralized email sending with error handling

        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_body: HTML content for email body
            email_type: Type of email for logging/errors (e.g., "verification email")
            username: Recipient username for logging
        """
        try:
            await self.http_manager.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.settings.resend_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": self.settings.from_email,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body,
                },
            )

            logger.info(
                f"{email_type.capitalize()} sent",
                extra={"to_email": to_email, "username": username},
            )
        except HTTPStatusError as e:
            self._handle_http_status_error(e, str(to_email), email_type)

        except HTTPError as e:
            # network errors, timeouts, etc.
            raise EmailDeliveryError(
                to_email=str(to_email),
                email_type=email_type,
                reason=f"Network error: {str(e)}",
            ) from e

    async def send_email_verification(
        self,
        magic_token: str,
        to_email: EmailStr,
        username: str,
        first_name: str,
        last_name: str,
    ):
        """Send email verification link"""
        link = f"{self.settings.app_url}/auth/verify_email?token={magic_token}"

        # TODO: Once UI development starts, build templates
        html_body = f"""
            <h2>Welcome to nānā-nalu! 🌊</h2>
            <p>Hey {first_name} {last_name}, your account: {username} has been created, click below to verify your email:</p>
            <a href="{link}">Verify Email</a>
            <p>This link expires in {self.settings.email_verification_expire_minutes} minutes.</p>
        """

        await self._send_email(
            to_email=to_email,
            subject="Verify your nānā-nalu account",
            html_body=html_body,
            email_type="verification email",
            username=username,
        )

    async def send_passsword_reset(
        self, magic_token: str, to_email: EmailStr, username: str
    ):
        """Send password reset link"""
        link = f"{self.settings.app_url}/auth/reset-password?token={magic_token}"

        # TODO: Once UI development starts, build templates
        html_body = f"""
            <h2>Password Reset Request</h2>
            <p>Hey {username}, click below to reset your password:</p>
            <a href="{link}">Reset Password</a>
            <p>This link expires in {self.settings.password_reset_expire_minutes} minutes.</p>
            <p>If you didn't request this, ignore this email.</p>
        """

        await self._send_email(
            to_email=to_email,
            subject="Reset your nānā-nalu password",
            html_body=html_body,
            email_type="password reset email",
            username=username,
        )
