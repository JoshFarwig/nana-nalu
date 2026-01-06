from typing import Literal
from pydantic import BaseModel, EmailStr


class RefreshToken(BaseModel):
    """Refresh tokens exchange request"""

    refresh_token: str


class Tokens(BaseModel):
    """Tokens structure returned by AuthService"""

    access_token: str
    refresh_token: str
    access_token_type: Literal["bearer"]


class TokenReponse(BaseModel):
    """Standard access token response for login/register/refresh routers"""

    access_token: str
    access_token_type: Literal["bearer"]


class UserEmailLogin(BaseModel):
    """Schema for user login via email"""

    email: EmailStr
    password: str


class UserUsernameLogin(BaseModel):
    """Schema for user login via username"""

    username: str
    password: str
