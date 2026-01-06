import jwt
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.security import SecurityManager
from core.dependencies.core import get_security_manager
from core.exceptions.auth import (
    InvalidAccessTokenError,
    TokenExpiredError,
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
            name=payload["name"],
            tier=payload["tier"],
            is_admin=payload["is_admin"],
        )

    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise InvalidAccessTokenError()

