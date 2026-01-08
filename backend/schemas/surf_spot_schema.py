from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Shared Base Models
# ============================================================================


class SurfSpotBase(BaseModel):
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True


# ============================================================================
# API Request Schemas
# ============================================================================


class SurfSpotCreate(SurfSpotBase):
    """Schema for creating a new surf spot using GeoJSON Point geometry."""

    geometry: dict = Field(
        description="GeoJSON Point geometry with coordinates [longitude, latitude]",
    )

    @field_validator("geometry")
    @classmethod
    def validate_point_geometry(cls, v: dict) -> dict:
        """Validate GeoJSON Point structure and coordinate ranges."""
        if v.get("type") != "Point":
            raise ValueError("geometry type must be 'Point'")

        coordinates = v.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError("Point coordinates must be [longitude, latitude]")

        lon, lat = coordinates
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            raise ValueError("coordinates must be numeric")

        # validate coordinate ranges
        if not -180 <= lon <= 180:
            raise ValueError(f"longitude must be between -180 and 180, got {lon}")
        if not -90 <= lat <= 90:
            raise ValueError(f"latitude must be between -90 and 90, got {lat}")

        return v


class SurfSpotUpdate(BaseModel):
    """Schema for updating a surf spot."""

    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    geometry: dict | None = Field(
        default=None,
        description="GeoJSON Point geometry with coordinates [longitude, latitude]",
    )
    is_active: bool | None = None

    @field_validator("geometry")
    @classmethod
    def validate_point_geometry(cls, v: dict | None) -> dict | None:
        """Validate GeoJSON Point structure and coordinate ranges."""
        if v is None:
            return v

        if v.get("type") != "Point":
            raise ValueError("geometry type must be 'Point'")

        coordinates = v.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError("Point coordinates must be [longitude, latitude]")

        lon, lat = coordinates
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            raise ValueError("coordinates must be numeric")

        # validate coordinate ranges
        if not -180 <= lon <= 180:
            raise ValueError(f"longitude must be between -180 and 180, got {lon}")
        if not -90 <= lat <= 90:
            raise ValueError(f"latitude must be between -90 and 90, got {lat}")

        return v


# ============================================================================
# API Response Schemas
# ============================================================================


class SurfSpotResponse(SurfSpotBase):
    """Schema for surf spot responses with GeoJSON geometry."""

    id: int
    created_by_id: int
    region: str
    geometry: dict  # GeoJSON point geometry

    model_config = {"from_attributes": True}
