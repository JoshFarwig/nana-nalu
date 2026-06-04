from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FieldMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str    # stable public slug, e.g. "wave_significant_height"
    path: str  # dot-path into ForecastPoint for value extraction, e.g. "wave.significant_height"
    label: str
    unit: str
    viz_type: Literal["scalar", "directional"]


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


class PointForecastResponse(BaseModel):
    provider: str
    model: str
    region: str
    run_time: datetime
    lat: float
    lon: float
    points: list[ForecastPoint]


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


class GridBounds(BaseModel):
    lat_min: float
    lat_max: float
    lon_min: float = Field(description="Longitude min (0-360)")
    lon_max: float = Field(description="Longitude max (0-360)")

    @field_validator("lat_min", "lat_max", "lon_min", "lon_max")
    @classmethod
    def _round(cls, v: float) -> float:
        return round(v, 6)


class TimeHorizon(BaseModel):
    start: datetime = Field(description="Earliest valid_time in run")
    end: datetime = Field(description="Latest valid_time in run")


class RegionInfo(BaseModel):
    id: str
    latest_run_time: datetime
    bounds: GridBounds
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
