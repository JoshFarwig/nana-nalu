from typing import Literal
from pydantic import BaseModel, EmailStr


# ============================================================================
# API Request Schemas
# ============================================================================


class UserEmailLogin(BaseModel):
    """Schema for user login via email"""

    email: EmailStr
    password: str


class UserUsernameLogin(BaseModel):
    """Schema for user login via username"""

    username: str
    password: str


class RefreshToken(BaseModel):
    """Refresh tokens exchange request"""

    refresh_token: str


# ============================================================================
# API Response Schemas
# ============================================================================


class AuthTokenReponse(BaseModel):
    """Standard access token response for login/register/refresh routers"""

    access_token: str
    access_token_type: Literal["bearer"]


# ============================================================================
# Internal DTOs (Service Layer)
# ============================================================================


class AuthTokens(BaseModel):
    """Tokens structure returned by AuthService (includes refresh_token for httpOnly cookie)"""

    access_token: str
    refresh_token: str
    access_token_type: Literal["bearer"]


class EnabledAccount(BaseModel):
    """Data structure returned by AuthService after enabling an Account"""

    user_id: int
    username: str
    email: EmailStr


class DisabledAccount(EnabledAccount):
    """Data structure returned by AuthService after disabling an Account"""

    sessions_revoked: int
