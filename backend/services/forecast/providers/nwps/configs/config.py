from datetime import time, timedelta, timezone
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, field_validator
from utils import Location

from .hawaii import NWPSMauiModel


def ensure_utc(t: time) -> time:
    """Validation helper method to ensure utc times"""
    if t.tzinfo is None:
        raise ValueError("Time must include tzinfo=timezone.utc")
    if t.tzinfo != timezone.utc:
        raise ValueError("Time must be UTC")
    return t


class WFOCode(str, Enum):
    """NOAA and NWPS Weather Forecast Office (WFO) codes"""

    HONOLULU = "HFO"


class NWPSGridConfig(BaseModel):
    """Grid selection for grib2 output from NWPS Models"""

    cg: str = Field(
        description="NWPS computational grid for a WFO (i.e. Maui's grid: CG4 for WFO: HFO)",
        pattern=r"^CG\d+$",
    )
    lat_max: float = Field(ge=-90, le=90, description="Northern latitude boundary")
    lat_min: float = Field(ge=-90, le=90, description="Southern latitude boundary")
    long_max: float = Field(ge=-180, le=180, description="Eastern longitude boundary")
    long_min: float = Field(ge=-180, le=180, description="Western longitude boundary")


class NWPSModelConfig(BaseModel):
    """Core NWPS model configuration that assists forecast orchestrating"""

    site_code: WFOCode = Field(description="NWPS Weather Forecast Office code")
    model_run_times: list[time] = Field(description="UTC times when model runs")
    model_long_wait_time: timedelta = Field(
        description="Initial long expected delay derived from models analysis time (i.e., 00Z, 12Z, etc.)"
    )
    model_short_wait_time: timedelta = Field(
        description="Short delay to poll for grib2 after initial long delay"
    )
    grib_filter_base_url: HttpUrl = Field(
        description="NOAA NOMADS GRIB filter service base url"
    )
    grid: NWPSGridConfig = Field(description="Geographic coverage area")

    @field_validator("model_run_times", mode="before")
    @classmethod
    def validate_model_run_times(cls, times):
        return all(ensure_utc(time) for time in times)


NWPS_MODELS: dict[Location, NWPSModelConfig] = {
    Location.MAUI: NWPSMauiModel(),
}
