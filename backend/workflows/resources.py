"""
Flow-scoped resource management for Prefect.

Resources are initialized once per flow run and shared across all tasks/subflows.
Subflows called via `await` share the same process and resources as the parent.
Only deployment-triggered flow runs spawn new subprocesses.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

from core.config import PrefectSettings, load_settings
from core.database import AsyncDatabaseManager
from core.http import AsyncHTTPManager
from core.redis import AsyncRedisManager


@dataclass
class ForecastResources:
    """
    Container for async resource managers used in forecast flows.

    Initialized once in the top-level orchestration flow, passed to all
    child flows and tasks. All run in the same process when using direct
    `await subflow()` calls.
    """

    http: AsyncHTTPManager
    redis: AsyncRedisManager
    db: AsyncDatabaseManager
    settings: PrefectSettings

    async def close(self) -> None:
        """Clean up all resources."""
        await self.http.close()
        await self.redis.close()
        await self.db.close()


@asynccontextmanager
async def forecast_resources(
    settings: PrefectSettings | None = None,
) -> AsyncGenerator[ForecastResources, None]:
    """
    Async context manager for flow-scoped resources.

    Usage:
        @flow
        async def orchestrate_nwps():
            async with forecast_resources() as resources:
                await process_region(region, resources)
    """
    if settings is None:
        settings = load_settings("prefect")

    http = AsyncHTTPManager(settings.http)
    redis = AsyncRedisManager(settings.redis, settings.redis.get_cache_url())
    db = AsyncDatabaseManager(settings.db)

    resources = ForecastResources(http=http, redis=redis, db=db, settings=settings)

    try:
        yield resources
    finally:
        await resources.close()
