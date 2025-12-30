from pydantic import BaseModel, Field


class SurfSpotBase(BaseModel):
    name: str = Field(max_length=100)
    description: str | None = Field(None, max_length=500)
    is_active: bool = True


class SurfSpotCreate(SurfSpotBase):
    """Schema for creating a new surf spot."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SurfSpotUpdate(BaseModel):
    """Schema for updating a surf spot."""

    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=500)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    is_active: bool | None = None


class SurfSpotResponse(SurfSpotBase):
    """Schema for surf spot responses with lat/lng extracted via PostGIS."""

    id: int
    created_by_id: int
    latitude: float
    longitude: float

    model_config = {"from_attributes": True}
