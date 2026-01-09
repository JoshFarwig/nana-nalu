import jwt
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.security import SecurityManager
from core.dependencies.core import get_security_manager
from core.exceptions.auth import (
    InvalidAccessTokenError,
    TokenExpiredError,
    InsufficientPermissionsError,
)
from schemas.user_schema import CurrentUser


http_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
    security_manager: SecurityManager = Depends(get_security_manager),
) -> CurrentUser:
    """Get current user data from JWT access token"""
    try:
        payload = security_manager.decode_access_token(credentials.credentials)

        return CurrentUser(
            user_id=payload["sub"],
            username=payload["username"],
            email=payload["email"],
            first_name=payload["first_name"],
            last_name=payload["last_name"],
            tier=payload["tier"],
            tier_id=payload["tier_id"],
            is_admin=payload["is_admin"],
        )

    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise InvalidAccessTokenError()


def require_admin(current_user: CurrentUser = Depends(get_current_user)):
    if not current_user.is_admin:
        raise InsufficientPermissionsError(
            details={
                "user_id": current_user.user_id,
                "username": current_user.username,
                "attempted_action": "admin_access",
            }
        )
