from datetime import timedelta
import logging
from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import EmailStr, SecretStr

from core.dependencies.services import (
    get_auth_service,
    get_magic_link_service,
)
from core.dependencies.auth import require_admin
from core.exceptions.auth import InvalidRefreshTokenError

from schemas.auth_schema import (
    UserEmailLogin,
    UserUsernameLogin,
    AuthTokenReponse,
)
from schemas.response_schema import SuccessResponse
from schemas.user_schema import UserCreate

from services.auth_service import AuthService
from services.magic_link_service import MagicLinkService, MagicLinkType
from utils.env import is_prod

logger = logging.getLogger(__name__)

# module level bool, decides if https is needed for refresh token
use_secure_cookies = is_prod()

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_token_cookie(
    refresh_token: str, max_age_days: int, response: Response
):
    """Helper method to set refresh token as httpOnly Cookie"""

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=use_secure_cookies,
        samesite="lax",  # allows for GET req on non-same site
        max_age=int(timedelta(days=max_age_days).total_seconds()),
        path="/api/v1/auth",
    )


@router.post("/register")
async def register(
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Start registration — sends verification email. No tokens issued yet."""

    await auth_service.register(user_data)

    return SuccessResponse(message="Check your email to complete registration")


@router.post("/verify-email")
async def verify_email(
    response: Response,
    token: str,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Complete registration — verifies email, creates user, issues tokens."""

    tokens = await auth_service.verify_email_and_create_user(token)

    _set_refresh_token_cookie(
        refresh_token=tokens.refresh_token,
        max_age_days=auth_service.settings.refresh_token_expire_days,
        response=response,
    )

    return SuccessResponse(
        message="Email verified and account created",
        data=AuthTokenReponse(
            access_token=tokens.access_token, access_token_type=tokens.access_token_type
        ),
    )


@router.post("/login")
async def login(
    response: Response,
    user_data: UserEmailLogin | UserUsernameLogin,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Login a user via the AuthService and issue out refresh + access tokens"""

    tokens = await auth_service.login(user_data)

    _set_refresh_token_cookie(
        refresh_token=tokens.refresh_token,
        max_age_days=auth_service.settings.refresh_token_expire_days,
        response=response,
    )

    return SuccessResponse(
        message="Succcesfully logged in",
        data=AuthTokenReponse(
            access_token=tokens.access_token, access_token_type=tokens.access_token_type
        ),
    )


@router.post("/refresh")
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Refresh both tokens (access + rotating refresh token)"""

    # check if refresh token exists in httpOnly cookie
    if not refresh_token:
        raise InvalidRefreshTokenError()

    tokens = await auth_service.refresh(refresh_token)

    _set_refresh_token_cookie(
        refresh_token=tokens.refresh_token,
        max_age_days=auth_service.settings.refresh_token_expire_days,
        response=response,
    )

    return SuccessResponse(
        message="Successfully refreshed access token",
        data=AuthTokenReponse(
            access_token=tokens.access_token, access_token_type=tokens.access_token_type
        ),
    )


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Logout user and clear refresh token cookie."""

    if refresh_token:
        await auth_service.logout(refresh_token)

    response.delete_cookie(key="refresh_token", path="/api/v1/auth")

    return SuccessResponse(message="Successfully logged out")


@router.post("/validate-link")
async def validate_magic_link(
    link_type: MagicLinkType,
    token: str,
    magic_link_service: MagicLinkService = Depends(get_magic_link_service),
):
    await magic_link_service.validate_link(link_type, token, consume=False)

    return SuccessResponse(message=f"Magic link ({link_type}) valid")


@router.post("/request-password-reset")
async def request_reset_password(
    email: EmailStr,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Issue out a reset password email"""

    await auth_service.request_password_reset_email(email)

    return SuccessResponse(message="Successfully sent password reset email")


@router.post("/reset-password")
async def reset_password(
    token: str,
    new_password: SecretStr,
    auth_service: AuthService = Depends(get_auth_service),
):
    await auth_service.reset_password(token, new_password)

    return SuccessResponse(message="Successfully reset user password")


@router.post("/enable-account/{user_id}", dependencies=[Depends(require_admin)])
async def enabled_account(
    user_id: int, auth_service: AuthService = Depends(get_auth_service)
):
    """Enable an account"""

    enabled_account = await auth_service.enable_account(user_id)

    return SuccessResponse(
        message=f"Enabled account for user: {user_id}-{enabled_account.username}",
        data=enabled_account,
    )


@router.post("/disable-account/{user_id}", dependencies=[Depends(require_admin)])
async def disable_account(
    user_id: int, auth_service: AuthService = Depends(get_auth_service)
):
    """Disable an account (switches is_active to False and revokes all sessions)"""

    disabled_account = await auth_service.disable_account(user_id)

    return SuccessResponse(
        message=(
            f"Disabled account for user: {user_id}-{disabled_account.username}, "
            f"revoked ({disabled_account.sessions_revoked}) session(s)"
        ),
        data=enabled_account,
    )


@router.post("/revoke-sessions/{user_id}", dependencies=[Depends(require_admin)])
async def revoke_sessions(
    user_id: int,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Revoke all sessions (refresh tokens) for a user"""

    sessions_revoked = await auth_service.revoke_all_sessions(user_id)
    return SuccessResponse(
        message=f"Successfully revoked {sessions_revoked} session(s) for user {user_id}",
        data={"sessions_revoked": sessions_revoked},
    )
