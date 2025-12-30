import logging

from core.redis import AsyncRedisManager
from core.exceptions.forecast import LocationNotSupportedError

from repositories.surf_spot_repository import AsyncSurfSpotRepository
from schemas.forecast_schema import ProviderForecast
from utils.location import Location

from services.forecast.providers.nomads.config import NOMADS_CONFIG_REGISTRY
from services.forecast.providers.pacioos.config import PACIOOS_CONFIG_REGISTRY


logger = logging.getLogger(__name__)


class ForecastService:
    """
    Service for retrieving forecast data from Redis.

    Responsibilities:
    - Discover available forecasts for a spot based on location
    - Retrieve forecast data from Redis
    - Return arrays of ProviderForecast objects
    """

    def __init__(
        self, redis_manager: AsyncRedisManager, surf_spot_repo: AsyncSurfSpotRepository
    ):
        self.redis = redis_manager
        self.surf_spot_repo = surf_spot_repo
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # =======================
    # HELPER FUNCTIONS
    # =======================

    def _get_all_registries(self) -> list:
        """Get all provider config registries."""
        return [NOMADS_CONFIG_REGISTRY, PACIOOS_CONFIG_REGISTRY]

    def _get_available_forecasts(self, location: Location) -> list[tuple[str, str]]:
        available = []

        for registry in self._get_all_registries():
            for (loc, model), config in registry.items():
                if loc == location:
                    available.append((config.provider_name, model.value))

        return available

    def _get_available_forecasts_grouped(
        self, location: Location
    ) -> dict[str, list[str]]:
        grouped = {}
        available = self._get_available_forecasts(location)

        for provider, model in available:
            if provider not in grouped:
                grouped[provider] = []
            grouped[provider].append(model)

        return grouped

    def _get_location_from_coordinates(self, lat: float, lon: float) -> Location | None:
        """
        Determine which Location a coordinate pair belongs to.

        Checks all provider registries to find matching grid bounds.
        Reuses _get_all_registries() to stay DRY.

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            Location enum if coordinates fall within a grid, None otherwise
        """
        checked_locations = set()

        for registry in self._get_all_registries():
            for (location, model), config in registry.items():
                # skip if we already checked this location
                if location in checked_locations:
                    continue

                checked_locations.add(location)
                grid = config.grid

                if (
                    grid.lat_min <= lat <= grid.lat_max
                    and grid.long_min <= lon <= grid.long_max
                ):
                    return location

        return None

    async def _get_spot_location(
        self, surf_spot_id: int
    ) -> tuple[float, float, Location]:
        """
        Get spot coordinates and determine its Location.

        Returns:
            Tuple of (latitude, longitude, Location)

        Raises:
            SurfSpotNotFoundError: If spot doesn't exist (raised by repository)
            LocationNotSupportedError: If spot not in supported region
        """
        # repository raises SurfSpotNotFoundError if spot doesn't exist
        coords = await self.surf_spot_repo.get_coordinates(surf_spot_id)

        lat = coords["latitude"]
        lon = coords["longitude"]

        location = self._get_location_from_coordinates(lat, lon)

        if not location:
            raise LocationNotSupportedError(surf_spot_id, lat, lon)

        return lat, lon, location

    async def fetch_forecast_from_redis(self, surf_spot_id: int):
        pass

    # =======================
    # PRIMARY FUNCTIONS
    # =======================

    async def get_forecasts(self, surf_spot_id: int):
        pass

    async def get_forecast_by_provider(self, surf_spot_id: int, provider: str):
        pass

    async def get_forecast_by_model(self, surf_spot_id: int, provider: str, model: str):
        pass

    async def get_available_providers(self, surf_spot_id: int):
        pass
