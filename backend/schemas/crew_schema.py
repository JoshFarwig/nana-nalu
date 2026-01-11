from datetime import datetime
from pydantic import BaseModel, Field

from models.crew_member_model import CrewRole


# ============================================================================
# Shared Base Models
# ============================================================================


class CrewBase(BaseModel):
    """Shared fields for crew schemas."""

    name: str = Field(min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=200)


# ============================================================================
# API Request Schemas
# ============================================================================


class CrewCreate(CrewBase):
    """Schema for creating a new crew."""

    pass


class CrewUpdate(BaseModel):
    """Schema for updating a crew (all fields optional)."""

    name: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=200)


# ============================================================================
# API Response Schemas
# ============================================================================


class CrewMemberResponse(BaseModel):
    """Schema for crew member in responses."""

    user_id: int
    username: str
    first_name: str
    last_name: str
    role: CrewRole
    joined_at: datetime

    model_config = {"from_attributes": True}


class CrewResponse(CrewBase):
    """Schema for crew responses."""

    id: int
    creator_id: int
    is_active: bool
    member_count: int
    max_members: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CrewDetailResponse(CrewResponse):
    """Schema for detailed crew response (includes members)."""

    members: list[CrewMemberResponse]


# ============================================================================
# Internal DTOs (Service Layer)
# ============================================================================
