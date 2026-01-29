from dataclasses import dataclass

from core.config import PrefectSettings, load_settings
from core.database import AsyncDatabaseManager
from core.http import AsyncHTTPManager
from core.redis import AsyncRedisManager


@dataclass
class ForecastResources:
    http: AsyncHTTPManager
    redis: AsyncRedisManager
    db: AsyncDatabaseManager
    settings: PrefectSettings

    async def close(self) -> None:
        """Clean up all resources."""
        await self.http.close()
        await self.redis.close()
        await self.db.close()


_RESOURCES: ForecastResources | None = None


async def get_resources() -> ForecastResources:
    """
    Lazy inits and return worker global resource singletons
    """
    global _RESOURCES
    if _RESOURCES is None:
        settings = load_settings("prefect")
        _RESOURCES = ForecastResources(
            http=AsyncHTTPManager(settings.http),
            redis=AsyncRedisManager(settings.redis, settings.redis.get_cache_url()),
            db=AsyncDatabaseManager(settings.db),
            settings=settings,
        )
    return _RESOURCES
