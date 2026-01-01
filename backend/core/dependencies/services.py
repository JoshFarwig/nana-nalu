import logging

from fastapi import Depends

from core.dependencies.core import get_async_redis_manager
from core.dependencies.repositories import get_surf_spot_repository
from core.redis import AsyncRedisManager
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from services.forecast.forecast_service import ForecastService

logger = logging.getLogger(__name__)


def get_forecast_service(
    redis_manager: AsyncRedisManager = Depends(get_async_redis_manager),
    surf_spot_repo: AsyncSurfSpotRepository = Depends(get_surf_spot_repository),
) -> ForecastService:
    return ForecastService(redis_manager, surf_spot_repo)
