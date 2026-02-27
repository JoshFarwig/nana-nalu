import logging

from core.redis import AsyncRedisManager
from core.exceptions.forecasts import (
    InvalidProviderError,
    InvalidModelError,
    NoForecastDataError,
)

from models.surf_spot_model import SurfSpot
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from services.forecast.forecast_schema import ProviderForecast
from services.policies.surf_spot_policy import SurfSpotPolicy
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
    - Enforce view-access policy on all public methods
    """

    def __init__(
        self,
        redis_manager: AsyncRedisManager,
        surf_spot_repo: AsyncSurfSpotRepository,
        policy: SurfSpotPolicy,
    ):
        self.redis = redis_manager
        self.surf_spot_repo = surf_spot_repo
        self.policy = policy

    async def get_forecasts(
        self, surf_spot_id: int, user_id: int
    ) -> list[ProviderForecast]:
        """
        Get all available forecasts for a surf spot.

        Returns:
            List of ProviderForecast objects from all available providers/models
            (returns empty list if no data available - client should check length)

        Raises:
            SurfSpotNotFoundError: If surf spot doesn't exist
            SurfSpotPermissionError: If user doesn't have view access
            LocationNotSupportedError: If region has no forecast coverage
        """
        spot = await self._get_spot(surf_spot_id, user_id)
        region = Region(spot.region)
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
                    f"No forecast data in Redis for {provider}:{model}:{region.value}:{surf_spot_id}",
                    extra={
                        "spot_id": surf_spot_id,
                        "provider": provider,
                        "model": model,
                        "region": region.value,
                    },
                )

        return forecasts

    async def get_forecast_by_provider(
        self, surf_spot_id: int, provider: str, user_id: int
    ) -> list[ProviderForecast]:
        """
        Get all forecasts from a specific provider for a surf spot.

        Returns:
            List of ProviderForecast objects from the specified provider
            (may include multiple models like tide, swan, wrf for pacioos)

        Raises:
            SurfSpotNotFoundError: If surf spot doesn't exist
            SurfSpotPermissionError: If user doesn't have view access
            InvalidProviderError: If provider is not available for this region
            NoForecastDataError: If no forecast data exists for any model from this provider
        """
        spot = await self._get_spot(surf_spot_id, user_id)
        region = Region(spot.region)
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
                logger.warning(
                    f"No forecast data in Redis for {provider}:{model}:{region.value}:{surf_spot_id}",
                    extra={
                        "spot_id": surf_spot_id,
                        "provider": provider,
                        "model": model,
                        "region": region.value,
                    },
                )

        # if no forecasts found for this provider, raise exception
        if not forecasts:
            raise NoForecastDataError(
                spot_id=surf_spot_id,
                provider=provider,
                reason=f"No models from {provider} have data available. Check if provider is running or data has expired.",
            )

        return forecasts

    async def get_forecast_by_model(
        self, surf_spot_id: int, provider: str, model: str, user_id: int
    ) -> ProviderForecast:
        """
        Get forecast from a specific provider's model for a surf spot.

        Returns:
            ProviderForecast object

        Raises:
            SurfSpotNotFoundError: If surf spot doesn't exist
            SurfSpotPermissionError: If user doesn't have view access
            InvalidProviderError: If provider is not available for this region
            InvalidModelError: If model is not available for this provider
            NoForecastDataError: If no forecast data exists for this specific model
        """
        spot = await self._get_spot(surf_spot_id, user_id)
        region = Region(spot.region)
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
            logger.warning(
                f"No forecast data in Redis for {provider}:{model}:{region.value}:{surf_spot_id}",
                extra={
                    "spot_id": surf_spot_id,
                    "provider": provider,
                    "model": model,
                    "region": region.value,
                    "redis_key": key,
                },
            )
            raise NoForecastDataError(
                spot_id=surf_spot_id,
                provider=provider,
                model=model,
                reason="Model run may have been skipped, data expired (TTL), or not yet available.",
            )

        return ProviderForecast.from_redis_json(data)

    async def get_forecasts_for_providers(
        self,
        spot_id: int,
        pairs: set[tuple[str, str]],
    ) -> dict[tuple[str, str], ProviderForecast | None]:
        """
        Fetch only the specific provider+model forecasts needed for condition evaluation.

        Does a single region DB lookup, then fetches all needed Redis keys in one
        pipeline round-trip rather than individual GETs.

        Args:
            spot_id: Surf spot ID
            pairs: Set of (provider, model) tuples to fetch

        Returns:
            {("nomads", "nwps"): ProviderForecast, ("pacioos", "tide"): None, ...}
            None value means data was not in Redis (missing/expired).
        """
        spot = await self.surf_spot_repo.get_by_id(spot_id)
        region = Region(spot.region)

        pairs_list = list(pairs)
        redis_keys = [
            self._build_redis_key(provider, model, region.value, spot_id)
            for provider, model in pairs_list
        ]

        async with self.redis.client.pipeline() as pipe:
            for key in redis_keys:
                pipe.get(key)
            results = await pipe.execute()

        lookup: dict[tuple[str, str], ProviderForecast | None] = {}
        for (provider, model), data in zip(pairs_list, results):
            if data:
                lookup[(provider, model)] = ProviderForecast.from_redis_json(data)
            else:
                logger.warning(
                    f"No forecast data in Redis for {provider}:{model}:{region.value}:{spot_id}",
                    extra={
                        "spot_id": spot_id,
                        "provider": provider,
                        "model": model,
                        "region": region.value,
                    },
                )
                lookup[(provider, model)] = None

        return lookup

    async def get_available_providers(
        self, surf_spot_id: int, user_id: int
    ) -> dict[str, list[str]]:
        """
        Get available forecast providers and their models for a surf spot.

        Returns:
            Dictionary mapping provider names to lists of available model names
            Example: {"nomads": ["nwps"], "pacioos": ["tide", "swan", "wrf"]}

        Raises:
            SurfSpotNotFoundError: If surf spot doesn't exist
            SurfSpotPermissionError: If user doesn't have view access
        """
        spot = await self._get_spot(surf_spot_id, user_id)
        region = Region(spot.region)
        return self._get_available_forecasts_grouped(region)

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

    async def _get_spot(self, surf_spot_id: int, user_id: int) -> SurfSpot:
        """
        Get surf spot and verify view access.

        Fetches the full ORM object (one query instead of the dict-based
        get_with_coordinates) and runs the policy check.

        Raises:
            SurfSpotNotFoundError: If spot doesn't exist
            SurfSpotPermissionError: If user doesn't have view access
        """
        spot = await self.surf_spot_repo.get_by_id(surf_spot_id)
        await self.policy.require_view_access(user_id, spot)
        return spot
