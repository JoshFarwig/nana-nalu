from datetime import datetime, time
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from utils.region import Region

if TYPE_CHECKING:
    from models import SurfSpot
    from services.forecast.forecast_schema import ProviderForecast


class ForecastProvider(Protocol):
    """Base protocol for all forecast providers."""

    provider_name: str

    @classmethod
    def supports_region(cls, region: Region) -> bool:
        """
        Check if this provider has configuration for the given region.

        Returns:
            True if provider can fetch data for this region, False otherwise.
        """
        ...

    def is_available_for_spot(self, spot: SurfSpot) -> bool:
        """Check if this provider can generate forecasts for the given spot."""
        ...


class FileProvider(ForecastProvider, Protocol):
    """
    Providers that download gridded data files (GRIB2, NetCDF etc.)
    and extract forecast data for multiple spots from a single file.
    """

    processing_mode: Literal["file"] = "file"

    def download_file(self, analysis_time: time) -> Path:
        """Download forecast file."""
        ...

    def extract_forecast(self, file_path: Path) -> dict[int, "ProviderForecast"]:
        """Extract forecast data for a avaiable spots from the regional file."""
        ...


class APIProvider(ForecastProvider, Protocol):
    """
    Providers accessed via HTTP APIs that return parsed data directly.
    """

    processing_mode: Literal["api"] = "api"
    supports_batching: bool  # can request multiple spots in one API call

    def fetch_forecast(self, timestamp: datetime) -> dict[int, "ProviderForecast"]:
        """Fetch forecast data via HTTP API for given spots."""
        ...


class StreamingDataProvider(ForecastProvider, Protocol):
    """
    Providers that stream gridded data via protocols like OPeNDAP/THREDDS.
    Data is subset server-side and loaded lazily.
    """

    processing_mode: Literal["stream"] = "stream"

    def fetch_forecasts(self) -> dict[int, "ProviderForecast"]:
        """
        Stream forecast data for all spots in the configured grid region.
        """
        ...
