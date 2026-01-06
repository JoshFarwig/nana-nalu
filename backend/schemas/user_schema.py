from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    username: str = Field(max_length=50)
    email: EmailStr = Field(max_length=100)
    name: str = Field(max_length=50)


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(min_length=8, max_length=256)


class AdminCreate(UserCreate):
    """Schema for creating a new user."""

    is_admin: bool = True


class UserUpdate(BaseModel):
    """Schema for updating a user (excludes password - use UserPasswordUpdate for that)."""

    username: str | None = Field(None, min_length=3, max_length=50)
    email: EmailStr | None = None
    name: str | None = Field(None, max_length=50)


class UserPasswordUpdate(BaseModel):
    """Schema for updating a user's password."""

    current_password: str = Field(min_length=8)
    new_password: str = Field(min_length=8, max_length=256)


class UserResponse(UserBase):
    """Schema for user responses (excludes password)."""

    id: int
    model_config = {"from_attributes": True}


class CurrentUser(BaseModel):
    """Schema representing the authenticated user from JWT token."""

    user_id: int
    username: str
    email: str
    name: str
    tier: str
    is_admin: bool
