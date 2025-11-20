from datetime import datetime, time
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from models import SurfSpot


class ForecastProvider(Protocol):
    """Base protocol for all forecast providers."""

    provider_name: str

    def is_available_for_spot(self, spot: SurfSpot) -> bool:
        """Check if this provider can generate forecasts for the given spot."""
        ...


class FileProvider(ForecastProvider, Protocol):
    """
    Providers that download gridded data files (GRIB2, NetCDF, etc.)
    and extract forecast data for multiple spots from a single file.
    """

    processing_mode: Literal["file"] = "file"

    def download_file(self, analysis_time: time) -> Path:
        """Download forecast file."""
        ...

    def extract_forecast(self, file_path: Path) -> dict:
        """Extract forecast data for a avaiable spots from the regional file."""
        ...


class APIProvider(ForecastProvider, Protocol):
    """
    Providers accessed via HTTP APIs that return parsed data directly.
    """

    processing_mode: Literal["api"] = "api"
    supports_batching: bool  # can request multiple spots in one API call

    # potientally consider async functionality, but for now, develop the
    # MVP with sync for celery
    def fetch_forecast(self, timestamp: datetime) -> dict[str, dict]:
        """Fetch forecast data via HTTP API for given spots."""
        ...
