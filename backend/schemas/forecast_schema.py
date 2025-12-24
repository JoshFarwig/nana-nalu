from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class ForecastProvider(str, Enum):
    """Data distribution organization for forecast data."""

    NOMADS = "nomads"  # NOAA Operational Model Archive and Distribution System
    PACIOOS = "pacioos"  # Pacific Islands Ocean Observing System


class ForecastModel(str, Enum):
    """Specific forecast model/system (generic, not region-specific)."""

    # NOMADS models
    NWPS = "nwps"  # Nearshore Wave Prediction System

    # PacIOOS models
    TIDE = "tide"  # Tidal predictions (astronomical harmonics)
    SWAN = "swan"  # Simulating WAves Nearshore
    WRF = "wrf"  # Weather Research and Forecasting (wind)


class WaveUnits(BaseModel):
    """Documents units for wave measurements."""

    model_config = ConfigDict(frozen=True)

    height: Literal["m"] = "m"
    height_swell: Literal["m"] = "m"
    direction_peak: Literal["degrees_true_from"] = "degrees_true_from"
    direction_mean: Literal["degrees_true_from"] = "degrees_true_from"
    period_peak: Literal["s"] = "s"
    period_mean: Literal["s"] = "s"


class WindUnits(BaseModel):
    """Documents units for wind measurements."""

    model_config = ConfigDict(frozen=True)

    speed: Literal["m/s"] = "m/s"
    direction: Literal["degrees_true_from"] = "degrees_true_from"


class CurrentUnits(BaseModel):
    """Documents units for current measurements."""

    model_config = ConfigDict(frozen=True)

    speed: Literal["m/s"] = "m/s"
    direction: Literal["degrees_true_toward"] = "degrees_true_toward"


class TideUnits(BaseModel):
    """Documents units for tide harmonics"""

    model_config = ConfigDict(frozen=True)

    height: Literal["m"] = "m"
    surge: Literal["m"] = "m"


class WaveData(BaseModel):
    """
    Unified wave measurements.

    All heights in meters, directions in degrees true (0-360, from),
    periods in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    # significant wave height (combined wind waves + swell)
    height: float | None = Field(
        default=None, description="Significant wave height (m)"
    )

    # swell component (deep water swell)
    height_swell: float | None = Field(default=None, description="Swell height (m)")

    # peak wave direction and period (most common from models)
    direction_peak: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Peak wave direction, degrees true (from)",
    )
    period_peak: float | None = Field(default=None, description="Peak wave period (s)")

    # mean wave direction and period (when available)
    direction_mean: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Mean wave direction, degrees true (from)",
    )
    period_mean: float | None = Field(default=None, description="Mean wave period (s)")


class WindData(BaseModel):
    """
    Unified wind measurements.

    Speed in m/s, direction in degrees true (0-360, from).
    """

    model_config = ConfigDict(extra="forbid")

    speed: float | None = Field(default=None, description="Wind speed (m/s)")
    direction: float | None = Field(
        default=None, ge=0, le=360, description="Wind direction, degrees true (from)"
    )


class CurrentData(BaseModel):
    """
    Unified ocean current measurements.

    Components in m/s, direction in degrees true (toward).
    """

    model_config = ConfigDict(extra="forbid")

    # derived polar form (computed from u,v velocity or provided directly)
    speed: float | None = Field(default=None, description="Current speed (m/s)")
    direction: float | None = Field(
        default=None, description="Current direction, degrees true (toward)"
    )


class TideData(BaseModel):
    """
    Unified tide level measurements.

    Represents tidal astronomical harmonics for a given location as well as
    any surge components from models

    """

    model_config = ConfigDict(frozen=True)

    height: float | None = Field(default=None, description="Tide height (m)")
    surge: float | None = Field(default=None, description="Surge height (m)")


class ForecastPoint(BaseModel):
    """
    Single forecast point in time with all available data.

    Not all fields populated for every provider - None categories excluded from JSON.
    """

    model_config = ConfigDict(extra="forbid")

    valid_time: datetime

    wave: WaveData | None = None
    wind: WindData | None = None
    current: CurrentData | None = None
    tide: TideData | None = None


class GridMetadata(BaseModel):
    """Grid selection metadata for file-based providers."""

    model_config = ConfigDict(extra="forbid")

    selected_lat: float
    selected_lon: float
    distance_km: float


class ProviderForecast(BaseModel):
    """
    Complete forecast from a single provider/model for a spot.

    This is what gets stored in Redis per provider:model:location combination.
    Key pattern: forecast:{provider}:{model}:{location}:{spot_id}
    """

    model_config = ConfigDict(extra="forbid")

    spot_id: int
    provider: ForecastProvider
    model: ForecastModel
    location: str = Field(description="Regional variant (e.g., maui, oahu, hawaii)")
    analysis_time: datetime | None = Field(
        default=None, description="Model run/analysis time (UTC)"
    )

    # grid metadata for file-based providers
    grid_metadata: GridMetadata | None = None

    # the forecast timeseries
    forecast: list[ForecastPoint]

    @staticmethod
    def get_units() -> dict:
        """Return units documentation for all measurements."""
        return {
            "wave": WaveUnits().model_dump(),
            "wind": WindUnits().model_dump(),
            "current": CurrentUnits().model_dump(),
            "tide": TideUnits().model_dump(),
        }

    def to_redis_json(self) -> str:
        """Serialize to JSON, excluding None values at all levels."""
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_redis_json(cls, data: str) -> "ProviderForecast":
        """Deserialize from Redis JSON string."""
        return cls.model_validate_json(data)
