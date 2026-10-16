from datetime import datetime
from typing import Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# Max decimals worth keeping for coordinates; also strips float-arithmetic
# noise from origin + n*res. ~0.11m at the equator — finer than any grid.
MAX_COORD_DP = 6


class FieldMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str  # stable public slug, e.g. "wave_significant_height"
    path: str  # dot-path into ForecastPoint for value extraction, e.g. "wave.significant_height"
    label: str
    unit: str
    viz_type: Literal["scalar", "directional"]  # how to paint the raster layer
    group: (
        str  # physical component, e.g. "combined_sea", "wind", "primary_swell", "tide"
    )
    role: Literal["magnitude", "direction", "scalar"]
    # FROM vs TOWARD reference frame for the arrow. Required iff role=="direction"
    # (meaningless otherwise): "from" = meteorological origin (wave/wind comes FROM),
    # "toward" = oceanographic travel (current flows TOWARD). Unset -> stripped by
    # response_model_exclude_none, so it's absent on the wire for non-direction fields.
    direction_convention: Literal["from", "toward"] | None = Field(default=None)

    @model_validator(mode="after")
    def validate_direction_convention(self) -> "FieldMeta":
        is_direction = self.role == "direction"
        has_convention = self.direction_convention is not None
        if is_direction and not has_convention:
            raise ValueError(
                f"FieldMeta {self.id!r}: role='direction' requires direction_convention"
            )
        if not is_direction and has_convention:
            raise ValueError(
                f"FieldMeta {self.id!r}: direction_convention only valid for role='direction'"
            )
        return self


class SwellPartition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    height: float | None = Field(default=None, description="Swell height (m)")
    period: float | None = Field(default=None, description="Swell period (s)")
    direction: float | None = Field(
        default=None, ge=0, le=360, description="Swell direction, degrees true (from)"
    )


class WaveData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    significant_height: float | None = Field(
        default=None, description="Significant wave height, combined (m)"
    )
    peak_period: float | None = Field(
        default=None, description="Peak period of dominant component (s)"
    )
    peak_direction: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Direction of dominant component, degrees true (from)",
    )
    wind_wave_height: float | None = Field(
        default=None, description="Significant height of wind waves (m)"
    )
    wind_wave_period: float | None = Field(
        default=None, description="Period of wind waves (s)"
    )
    wind_wave_direction: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Direction of wind waves, degrees true (from)",
    )
    primary_swell: SwellPartition | None = Field(
        default=None, description="Dominant swell system"
    )
    secondary_swell: SwellPartition | None = Field(
        default=None, description="Second swell system"
    )
    tertiary_swell: SwellPartition | None = Field(
        default=None, description="Third swell system"
    )


class WindData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed: float | None = Field(default=None, description="Wind speed (m/s)")
    direction: float | None = Field(
        default=None, ge=0, le=360, description="Wind direction, degrees true (from)"
    )


class CurrentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed: float | None = Field(default=None, description="Current speed (m/s)")
    direction: float | None = Field(
        default=None, description="Current direction, degrees true (toward)"
    )


class TideData(BaseModel):
    model_config = ConfigDict(frozen=True)

    height: float | None = Field(default=None, description="Tide height (m)")


class ForecastPoint(BaseModel):
    """Single forecast timestep. Re-validated from JSONB on API read path."""

    model_config = ConfigDict(extra="forbid")

    valid_time: datetime
    wave: WaveData | None = None
    wind: WindData | None = None
    tide: TideData | None = None
    current: CurrentData | None = None


# ======================================================
# API Response Models
# ======================================================


class GridForecastRow(BaseModel):
    lat: float
    lon: float
    payload: dict


class GridForecastResponse(BaseModel):
    provider: str
    model: str
    region: str
    run_time: datetime
    rows: list[GridForecastRow]


class CoordBounds(BaseModel):
    lat_min: float
    lat_max: float
    lon_min: float = Field(description="Longitude min (0-360)")
    lon_max: float = Field(description="Longitude max (0-360)")

    @field_validator("lat_min", "lat_max", "lon_min", "lon_max")
    @classmethod
    def _round(cls, v: float) -> float:
        # Float-noise floor for any bounds (region extents, OOB grids).
        # Cell bounds are already rounded per-resolution upstream; this is
        # idempotent on those since res precision never exceeds MAX_COORD_DP.
        return round(v, MAX_COORD_DP)


class TimeHorizon(BaseModel):
    start: datetime = Field(description="Earliest valid_time in run")
    end: datetime = Field(description="Latest valid_time in run")


class RegionInfo(BaseModel):
    id: str
    latest_run_time: datetime
    region_bounds: CoordBounds
    horizon: TimeHorizon


class ModelInfo(BaseModel):
    id: str
    fields: list[FieldMeta]
    regions: list[RegionInfo]


class ProviderInfo(BaseModel):
    id: str
    models: list[ModelInfo]


class AvailableRunsResponse(BaseModel):
    providers: list[ProviderInfo]


class PointForecastResponse(BaseModel):
    provider: str
    model: str
    region: str
    run_time: datetime
    lat: float
    lon: float
    cell_bounds: CoordBounds
    points: list[ForecastPoint]
