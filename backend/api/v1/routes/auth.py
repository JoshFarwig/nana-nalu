from datetime import timedelta
import logging
from fastapi import APIRouter, Cookie, Depends, Response

from core.dependencies.repositories import get_user_repository
from core.dependencies.services import get_auth_service
from core.dependencies.auth import require_admin
from core.exceptions.auth import InvalidRefreshTokenError

from repositories.user_repository import AsyncUserRepository
from schemas.auth_schema import (
    UserEmailLogin,
    UserUsernameLogin,
    AuthTokenReponse,
)
from schemas.response_schema import SuccessResponse
from schemas.user_schema import UserCreate

from services.auth_service import AuthService

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
    response: Response,
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Register a new user via the AuthService and issue out refresh + access tokens"""

    tokens = await auth_service.register(user_data)

    _set_refresh_token_cookie(
        refresh_token=tokens.refresh_token,
        max_age_days=auth_service.settings.refresh_token_expire_days,
        response=response,
    )

    return SuccessResponse(
        message="Successfully registered account",
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


@router.post("/disable_account/{user_id}", dependencies=[Depends(require_admin)])
async def disable_account(
    user_id: int, user_repo: AsyncUserRepository = Depends(get_user_repository)
):
    """Disable an account"""
    user = await user_repo.update(user_id, user_data={"is_active": False})
    await user_repo.session.commit()

    logger.warning(
        f"Disabled account: {user_id}",
        extra={
            "user_id": user.id,
        },
    )

    return SuccessResponse()


@router.post("/revoke_sessions/{user_id}", dependencies=[Depends(require_admin)])
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
