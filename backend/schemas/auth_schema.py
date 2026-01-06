from typing import Literal
from pydantic import BaseModel, EmailStr


class RefreshToken(BaseModel):
    """Refresh token exchange request"""

    refresh_token: str


class TokenResponse(BaseModel):
    """Standard token response on login/register/refresh"""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"]


class UserEmailLogin(BaseModel):
    """Schema for user login via email"""

    email: EmailStr
    password: str


class UserUsernameLogin(BaseModel):
    """Schema for user login via username"""

    username: str
    password: str
