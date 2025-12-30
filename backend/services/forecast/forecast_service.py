from core.redis import AsyncRedisManager
from repositories.surf_spot_repository import AsyncSurfSpotRepository


class ForecastService:
    def __init__(
        self, redis_manager: AsyncRedisManager, surf_spot_repo: AsyncSurfSpotRepository
    ):
        self.redis = redis_manager
        self.surf_spot_repo = surf_spot_repo

    def get_all_forecasts(self, surf_spot_id: int):
        pass

    def get_all_provider_models():
        pass
