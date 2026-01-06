import logging

from fastapi import Depends

from core.config import APISettings
from core.dependencies.core import get_async_redis_manager, get_settings
from core.dependencies.repositories import (
    get_account_tier_repository,
    get_surf_spot_repository,
    get_user_repository,
)
from core.redis import AsyncRedisManager
from repositories.account_tier_repository import AsyncAccountTierRepository
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from repositories.user_repository import AsyncUserRepository
from services.auth_service import AuthService
from services.forecast.forecast_service import ForecastService

logger = logging.getLogger(__name__)


def get_auth_service(
    user_repo: AsyncUserRepository = Depends(get_user_repository),
    tier_repo: AsyncAccountTierRepository = Depends(get_account_tier_repository),
    settings: APISettings = Depends(get_settings),
) -> AuthService:
    return AuthService(user_repo, tier_repo, settings)


def get_forecast_service(
    redis_manager: AsyncRedisManager = Depends(get_async_redis_manager),
    surf_spot_repo: AsyncSurfSpotRepository = Depends(get_surf_spot_repository),
) -> ForecastService:
    return ForecastService(redis_manager, surf_spot_repo)
