from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class ForecastProvider(str, Enum):
    """Source provider for forecast data."""

    NWPS = "nwps"
    PACIOOS_ROMS = "pacioos_roms"


class WaveData(BaseModel):
    """
    Unified wave measurements.

    All heights in meters, directions in degrees true (0-360, from),
    periods in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    # Primary/significant wave height (combined wind waves + swell)
    height: float | None = Field(None, description="Significant wave height (m)")

    # Direction - prefer peak/primary, fallback to mean
    direction: float | None = Field(
        None, description="Wave direction, degrees true (from)"
    )

    # Period - prefer peak/primary, fallback to mean
    period: float | None = Field(None, description="Wave period (s)")

    # Extended fields when available
    height_swell: float | None = Field(None, description="Swell-only height (m)")
    direction_mean: float | None = Field(
        None, description="Mean wave direction (degrees)"
    )
    direction_peak: float | None = Field(
        None, description="Peak wave direction (degrees)"
    )
    period_mean: float | None = Field(None, description="Mean wave period (s)")
    period_peak: float | None = Field(None, description="Peak wave period (s)")


class WindData(BaseModel):
    """
    Unified wind measurements.

    Speed in m/s, direction in degrees true (0-360, from).
    """

    model_config = ConfigDict(extra="forbid")

    speed: float | None = Field(None, description="Wind speed (m/s)")
    direction: float | None = Field(
        None, description="Wind direction, degrees true (from)"
    )

    # Derived for UI convenience
    speed_kts: float | None = Field(None, description="Wind speed (knots)")


class CurrentData(BaseModel):
    """
    Unified ocean current measurements.

    Components in m/s, direction in degrees true (toward).
    """

    model_config = ConfigDict(extra="forbid")

    # Raw components (when available from ROMS)
    u: float | None = Field(None, description="Eastward velocity (m/s)")
    v: float | None = Field(None, description="Northward velocity (m/s)")

    # Derived polar form (computed from u,v or provided directly)
    speed: float | None = Field(None, description="Current speed (m/s)")
    direction: float | None = Field(
        None, description="Current direction, degrees true (toward)"
    )


class TideData(BaseModel):
    """
    Unified tide/sea level measurements.

    Heights relative to datum (typically MLLW), in meters.
    """

    model_config = ConfigDict(extra="forbid")

    height: float | None = Field(None, description="Sea surface height (m)")

    # Tide state for UI (computed from height timeseries)
    state: str | None = Field(None, description="rising, falling, high, low")
    next_high: datetime | None = Field(None, description="Next high tide time")
    next_low: datetime | None = Field(None, description="Next low tide time")


class ForecastPoint(BaseModel):
    """
    Single forecast point in time with all available data.

    Not all fields populated for every provider - None categories excluded from JSON.
    """

    model_config = ConfigDict(extra="forbid")

    valid_time: datetime = Field(..., description="Forecast valid time (UTC)")

    wave: WaveData | None = None
    wind: WindData | None = None
    current: CurrentData | None = None
    tide: TideData | None = None


class GridMetadata(BaseModel):
    """Grid selection metadata for file-based providers."""

    model_config = ConfigDict(extra="forbid")

    selected_lat: float = Field(..., description="Selected grid latitude")
    selected_lon: float = Field(..., description="Selected grid longitude")
    distance_km: float = Field(..., description="Distance from spot to grid point (km)")


class ProviderForecast(BaseModel):
    """
    Complete forecast from a single provider for a spot.

    This is what gets stored in Redis per provider.
    """

    model_config = ConfigDict(extra="forbid")

    spot_id: int
    provider: ForecastProvider
    analysis_time: datetime = Field(..., description="Model run/analysis time (UTC)")

    # Grid metadata for file-based providers
    grid_metadata: GridMetadata | None = None

    # The forecast timeseries
    forecast: list[ForecastPoint]

    def to_redis_json(self) -> str:
        """Serialize to JSON, excluding None values at all levels."""
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_redis_json(cls, data: str) -> "ProviderForecast":
        """Deserialize from Redis JSON string."""
        return cls.model_validate_json(data)
