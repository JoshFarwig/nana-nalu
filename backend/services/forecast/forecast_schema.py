from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

from utils.region import Region


# ============================================================================
# Shared Models (Used by both Internal DTOs and API Responses)
# ============================================================================


class ForecastProvider(str, Enum):
    """Data distribution organization for forecast data."""

    NOMADS = "nomads"  # NOAA Operational Model Archive and Distribution System
    PACIOOS = "pacioos"  # Pacific Islands Ocean Observing System


class ForecastModel(str, Enum):
    """Specific forecast model/system (generic, not region-specific)."""

    # NOMADS models
    NWPS = "nwps"  # Nearshore Wave Prediction System
    GFS_WAVE = "gfs_wave"  # Global Forecast System Wave Model

    # PacIOOS models
    TIDE = "tide"  # Tidal predictions (astronomical harmonics)
    SWAN = "swan"  # Simulating WAves Nearshore
    WRF = "wrf"  # Weather Research and Forecasting (wind)
    WAVEWATCH3 = "wavewatch3"  # WaveWatch III Wave Model


class WaveUnits(BaseModel):
    """Documents units for wave measurements."""

    model_config = ConfigDict(frozen=True)

    # Total sea state
    significant_height: Literal["m"] = "m"
    peak_period: Literal["s"] = "s"
    peak_direction: Literal["degrees_true_toward"] = "degrees_true_toward"

    # Wind waves
    wind_wave_height: Literal["m"] = "m"
    wind_wave_period: Literal["s"] = "s"
    wind_wave_direction: Literal["degrees_true_toward"] = "degrees_true_toward"

    # Swell components (applies to all partitions)
    swell_height: Literal["m"] = "m"
    swell_period: Literal["s"] = "s"
    swell_direction: Literal["degrees_true_toward"] = "degrees_true_toward"


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


class SwellPartition(BaseModel):
    """
    Individual swell component with direction, period, and height.

    Represents a single swell system (e.g., west swell, south swell).
    """

    model_config = ConfigDict(extra="forbid")

    height: float | None = Field(default=None, description="Swell height (m)")
    period: float | None = Field(default=None, description="Swell period (s)")
    direction: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Swell direction, degrees true (toward)",
    )


class WaveData(BaseModel):
    """
    Unified wave measurements representing complete sea state.

    Includes total combined conditions, wind-generated waves,
    and individual swell partitions ordered by energy/significance.

    All heights in meters, directions in degrees true (0-360, toward),
    periods in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    # ===== Total Sea State (All Components Combined) =====
    significant_height: float | None = Field(
        default=None,
        description="Significant wave height - combined wind waves and all swells (m)",
    )
    peak_period: float | None = Field(
        default=None, description="Peak period of dominant wave component (s)"
    )
    peak_direction: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Direction of dominant wave component, degrees true (toward)",
    )

    # ===== Wind Waves (Locally Generated) =====
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
        description="Direction of wind waves, degrees true (toward)",
    )

    # ===== Swell Partitions (Remotely Generated) =====
    # Ordered by significance: primary > secondary > tertiary
    primary_swell: SwellPartition | None = Field(
        default=None, description="Dominant swell system"
    )
    secondary_swell: SwellPartition | None = Field(
        default=None, description="Second most significant swell system"
    )
    tertiary_swell: SwellPartition | None = Field(
        default=None, description="Third swell system (rare, only from some models)"
    )


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


class ForecastPoint(BaseModel):
    """
    Single forecast point in time with all available data.

    Not all fields populated for every provider - None categories excluded from JSON.
    """

    model_config = ConfigDict(extra="forbid")

    valid_time: datetime

    wave: WaveData | None = None
    wind: WindData | None = None
    tide: TideData | None = None
    current: CurrentData | None = None


# ============================================================================
# Internal DTOs (Redis Storage)
# ============================================================================


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
    region: Region = Field(description="Regional variant (e.g., maui, oahu, hawaii)")
    analysis_time: datetime | None = Field(
        default=None, description="Model run/analysis time (UTC)"
    )

    # grid metadata for file-based providers
    grid_metadata: GridMetadata | None = None

    # category-level descriptions of what data represents (from provider config)
    data_summary: dict[str, str] | None = Field(
        default=None,
        description="Human-readable descriptions of data categories (e.g., tide methodology)",
    )

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


# ============================================================================
# API Response Schemas
# ============================================================================


class ProviderForecastResponse(BaseModel):
    """
    API response schema for forecast data.
    """

    model_config = ConfigDict(extra="forbid")

    provider: ForecastProvider
    model: ForecastModel
    region: Region = Field(description="Regional variant (e.g., maui, oahu, hawaii)")
    analysis_time: datetime | None = Field(
        default=None, description="Model run/analysis time (UTC)"
    )

    # grid metadata for file-based providers
    grid_metadata: GridMetadata | None = None

    # category-level descriptions of what data represents (from provider config)
    data_summary: dict[str, str] | None = Field(
        default=None,
        description="Human-readable descriptions of data categories (e.g., 'tide: Astronomical predictions only')",
    )

    # the forecast timeseries
    forecast: list[ForecastPoint]

    def _compute_units(self) -> dict[str, dict[str, str]]:
        """
        Compute units based on what specific fields have non-null values.
        Only includes units for fields that actually contain data across the forecast.
        """
        units_map = {}

        # collect which specific fields have non-null values for each category
        wave_fields = set()
        wind_fields = set()
        tide_fields = set()
        current_fields = set()

        for point in self.forecast:
            if point.wave:
                wave_data = point.wave.model_dump(exclude_none=True)
                # Flatten swell partition keys to unit field names
                for swell_key in ("primary_swell", "secondary_swell", "tertiary_swell"):
                    if swell_key in wave_data:
                        swell_data = wave_data.pop(swell_key)
                        if "height" in swell_data:
                            wave_data["swell_height"] = True
                        if "period" in swell_data:
                            wave_data["swell_period"] = True
                        if "direction" in swell_data:
                            wave_data["swell_direction"] = True
                wave_fields.update(wave_data.keys())
            if point.wind:
                wind_data = point.wind.model_dump(exclude_none=True)
                wind_fields.update(wind_data.keys())
            if point.tide:
                tide_data = point.tide.model_dump(exclude_none=True)
                tide_fields.update(tide_data.keys())
            if point.current:
                current_data = point.current.model_dump(exclude_none=True)
                current_fields.update(current_data.keys())

        # build units dict with only the fields that have data
        all_wave_units = WaveUnits().model_dump()
        all_wind_units = WindUnits().model_dump()
        all_tide_units = TideUnits().model_dump()
        all_current_units = CurrentUnits().model_dump()

        if wave_fields:
            units_map["wave"] = {
                k: v for k, v in all_wave_units.items() if k in wave_fields
            }
        if wind_fields:
            units_map["wind"] = {
                k: v for k, v in all_wind_units.items() if k in wind_fields
            }
        if tide_fields:
            units_map["tide"] = {
                k: v for k, v in all_tide_units.items() if k in tide_fields
            }
        if current_fields:
            units_map["current"] = {
                k: v for k, v in all_current_units.items() if k in current_fields
            }

        return units_map

    def to_response_dict(self) -> dict:
        """
        Convert to clean response dictionary with:
        - All None values excluded recursively
        - Dynamically computed units based on available fields
        """
        data = self.model_dump(exclude_none=True, mode="json")
        data["units"] = self._compute_units()
        return data

    @staticmethod
    def get_units() -> dict:
        """Return units documentation for all measurements."""
        return {
            "wave": WaveUnits().model_dump(),
            "wind": WindUnits().model_dump(),
            "current": CurrentUnits().model_dump(),
            "tide": TideUnits().model_dump(),
        }

    @classmethod
    def from_provider_forecast(cls, pf: ProviderForecast) -> "ProviderForecastResponse":
        """Convert internal ProviderForecast to API response schema."""
        return cls(
            provider=pf.provider,
            model=pf.model,
            region=pf.region,
            analysis_time=pf.analysis_time,
            grid_metadata=pf.grid_metadata,
            data_summary=pf.data_summary,
            forecast=pf.forecast,
        )
