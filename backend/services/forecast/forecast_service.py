import logging

from core.redis import AsyncRedisManager
from core.exceptions.forecast import (
    InvalidProviderError,
    InvalidModelError,
)

from repositories.surf_spot_repository import AsyncSurfSpotRepository
from schemas.forecast_schema import ProviderForecast
from utils.region import Region

from services.forecast.config_registries import provider_config_registries


logger = logging.getLogger(__name__)


class ForecastService:
    """
    Service for retrieving forecast data from Redis.

    Responsibilities:
    - Discover available forecasts for a spot based on its region
    - Retrieve forecast data from Redis
    - Return arrays of ProviderForecast objects
    """

    def __init__(
        self, redis_manager: AsyncRedisManager, surf_spot_repo: AsyncSurfSpotRepository
    ):
        self.redis = redis_manager
        self.surf_spot_repo = surf_spot_repo

    # =======================
    # PRIMARY FUNCTIONS
    # =======================

    async def get_forecasts(self, surf_spot_id: int) -> list[ProviderForecast]:
        """
        Get all available forecasts for a surf spot.

        Returns:
            List of ProviderForecast objects from all available providers/models

        Raises:
            SurfSpotNotFoundError: If surf spot doesn't exist
            LocationNotSupportedError: If region has no forecast coverage
        """
        region = await self._get_spot_region(surf_spot_id)
        available = self._get_available_providers_and_models(region)

        forecasts = []
        for provider, model in available:
            key = self._build_redis_key(provider, model, region.value, surf_spot_id)
            data = await self.redis.client.get(key)

            if data:
                forecast = ProviderForecast.from_redis_json(data)
                forecasts.append(forecast)
            else:
                logger.warning(
                    f"No forecast data in Redis for {provider}:{model}:{region.value}:{surf_spot_id}"
                )

        return forecasts

    async def get_forecast_by_provider(
        self, surf_spot_id: int, provider: str
    ) -> list[ProviderForecast]:
        """
        Get all forecasts from a specific provider for a surf spot.

        Returns:
            List of ProviderForecast objects from the specified provider
            (may include multiple models like tide, swan, wrf for pacioos)

        Raises:
            SurfSpotNotFoundError: If surf spot doesn't exist
            InvalidProviderError: If provider is not available for this region
        """
        region = await self._get_spot_region(surf_spot_id)
        available_grouped = self._get_available_forecasts_grouped(region)

        # validate provider exists for this region
        if provider not in available_grouped:
            available_providers = list(available_grouped.keys())
            raise InvalidProviderError(provider, available_providers)

        # fetch all models for this provider
        forecasts = []
        for model in available_grouped[provider]:
            key = self._build_redis_key(provider, model, region.value, surf_spot_id)
            data = await self.redis.client.get(key)

            if data:
                forecast = ProviderForecast.from_redis_json(data)
                forecasts.append(forecast)
            else:
                logger.debug(
                    f"No forecast data in Redis for forecast:{provider}:{model}:{region.value}:{surf_spot_id}"
                )

        return forecasts

    async def get_forecast_by_model(
        self, surf_spot_id: int, provider: str, model: str
    ) -> ProviderForecast | None:
        """
        Get forecast from a specific provider's model for a surf spot.

        Returns:
            ProviderForecast object if data exists, None otherwise

        Raises:
            SurfSpotNotFoundError: If surf spot doesn't exist
            InvalidProviderError: If provider is not available for this region
            InvalidModelError: If model is not available for this provider
        """
        region = await self._get_spot_region(surf_spot_id)
        available_grouped = self._get_available_forecasts_grouped(region)

        # validate provider exists for this region
        if provider not in available_grouped:
            available_providers = list(available_grouped.keys())
            raise InvalidProviderError(provider, available_providers)

        # validate model exists for this provider
        if model not in available_grouped[provider]:
            available_models = available_grouped[provider]
            raise InvalidModelError(model, provider, available_models)

        # fetch the specific forecast
        key = self._build_redis_key(provider, model, region.value, surf_spot_id)
        data = await self.redis.client.get(key)

        if not data:
            logger.debug(
                f"No forecast data in Redis for forecast:{provider}:{model}:{region.value}:{surf_spot_id}"
            )
            return None

        return ProviderForecast.from_redis_json(data)

    async def get_available_providers(self, surf_spot_id: int) -> dict[str, list[str]]:
        """
        Get available forecast providers and their models for a surf spot.

        Returns:
            Dictionary mapping provider names to lists of available model names
            Example: {"nomads": ["nwps"], "pacioos": ["tide", "swan", "wrf"]}

        Raises:
            SurfSpotNotFoundError: If surf spot doesn't exist
        """
        region = await self._get_spot_region(surf_spot_id)
        return self._get_available_forecasts_grouped(region)

    # =======================
    # HELPER FUNCTIONS
    # =======================

    def _build_redis_key(
        self, provider: str, model: str, region: str, spot_id: int
    ) -> str:
        """Build Redis key for forecast data."""
        return f"forecast:{provider}:{model}:{region}:{spot_id}"

    def _get_available_providers_and_models(
        self, region: Region
    ) -> list[tuple[str, str]]:
        available = []

        for registry in provider_config_registries:
            for (r, model), config in registry.items():
                if r == region:
                    available.append((config.provider_name, model.value))

        return available

    def _get_available_forecasts_grouped(self, region: Region) -> dict[str, list[str]]:
        """Group available forecasts by provider."""
        grouped = {}
        available = self._get_available_providers_and_models(region)

        for provider, model in available:
            if provider not in grouped:
                grouped[provider] = []
            grouped[provider].append(model)

        return grouped

    async def _get_spot_region(self, surf_spot_id: int) -> Region:
        """
        Get the region for a surf spot.

        Reads the pre-computed region directly from the spot record.
        Region is set at spot creation time based on coordinates.

        Raises:
            SurfSpotNotFoundError: If spot doesn't exist
        """
        spot = await self.surf_spot_repo.get_with_coordinates(surf_spot_id)

        return Region(spot["region"])
