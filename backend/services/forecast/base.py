from datetime import datetime, time
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from models import SurfSpot


class ForecastProvider(Protocol):
    """Base protocol for all forecast providers."""

    provider_name: str
    update_frequency_hours: time  # how often the provider updates their data

    def is_available_for_spot(self, spot: SurfSpot) -> bool:
        """Check if this provider can generate forecasts for the given spot."""
        ...


class FileProvider(ForecastProvider, Protocol):
    """
    Providers that download gridded data files (GRIB2, NetCDF, etc.)
    and extract forecast data for multiple spots from a single file.
    """

    processing_mode: Literal["file"] = "file"

    async def download_regional_file(self, region: str, model_run: datetime) -> Path:
        """Download forecast file for a region."""
        ...

    async def extract_spot_data(
        self, file_path: Path, spot: SurfSpot, model_run: datetime
    ) -> dict:
        """Extract forecast data for a single spot from the regional file."""
        ...


class APIProvider(ForecastProvider, Protocol):
    """
    Providers accessed via HTTP APIs that return parsed data directly.
    """

    processing_mode: Literal["api"] = "api"
    supports_batching: bool  # can request multiple spots in one API call

    async def fetch_forecast(
        self, spots: list[SurfSpot], timestamp: datetime
    ) -> dict[str, dict]:
        """Fetch forecast data via HTTP API for given spots."""
        ...
