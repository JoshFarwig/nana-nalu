from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ============================================================================
# Shared Base Models
# ============================================================================


class UserBase(BaseModel):
    """Only truly shared required fields across all user schemas."""

    username: str = Field(min_length=8, max_length=25)
    email: EmailStr
    first_name: str = Field(max_length=25)
    last_name: str = Field(max_length=25)


# ============================================================================
# API Request Schemas
# ============================================================================


class UserCreate(UserBase):
    """Schema for creating a new user via registration."""

    password: str = Field(min_length=8, max_length=256)


class UserUpdate(BaseModel):
    """Schema for updating a user profile (excludes password - use UserPasswordUpdate for that)."""

    email: EmailStr | None = Field(default=None)
    username: str | None = Field(default=None, min_length=8, max_length=25)
    first_name: str | None = Field(default=None, max_length=25)
    last_name: str | None = Field(default=None, max_length=25)
    bio: str | None = Field(default=None, max_length=150)


class UserPasswordUpdate(BaseModel):
    """Schema for updating a user's password."""

    new_password: str = Field(min_length=8, max_length=256)


# ============================================================================
# API Response Schemas
# ============================================================================


class UserResponse(UserBase):
    """Schema for user responses (excludes password)."""

    bio: str | None = Field(default=None, max_length=150)
    model_config = {"from_attributes": True}


# ============================================================================
# Internal DTOs (JWT Token Payload)
# ============================================================================


class CurrentUser(BaseModel):
    """Schema representing the authenticated user from JWT token."""

    user_id: int
    username: str
    email: str
    first_name: str
    last_name: str
    tier: str
    tier_id: int
    is_admin: bool
