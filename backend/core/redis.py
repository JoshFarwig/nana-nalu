import logging
import redis.asyncio as aioredis

from core.configs.redis_config import RedisConfig


class AsyncRedisManager:
    def __init__(self, settings: RedisConfig, db_url: str):
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.redis_url = db_url
        self._client: aioredis.Redis | None = None

    def _create_client(self) -> aioredis.Redis:
        """Create Redis client with connection pooling."""
        return aioredis.from_url(
            self.redis_url,
            max_connections=self.settings.async_max_connections,
            socket_connect_timeout=self.settings.async_connect_timeout,
            socket_timeout=self.settings.async_socket_timeout,
            encoding="utf-8",
            decode_responses=self.settings.decode_responses,
            retry_on_timeout=self.settings.retry_on_timeout,
        )

    @property
    def client(self) -> aioredis.Redis:
        """Get Redis client, creating if necessary."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    async def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            await self.client.ping()  # type: ignore[] (pyright not recognizing | Awaitable(bool))
            return True
        except Exception as e:
            self.logger.error("Health check failed", exc_info=e)
            return False

    async def close(self) -> None:
        """Close Redis connections."""
        if self._client:
            await self._client.aclose()
            self._client = None
