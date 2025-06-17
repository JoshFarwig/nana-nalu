from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    username: str = Field(..., max_length=50)
    email: EmailStr = Field(..., max_length=100)
    first_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(..., min_length=8, max_length=256)


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    password: Optional[str] = Field(None, min_length=8)


class UserResponse(UserBase):
    """Schema for user responses (excludes password)."""

    id: int

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    """Schema for user login."""

    username_or_email: str
    password: str
