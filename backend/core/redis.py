import json
import logging
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import Redis

from backend.core.config import BaseConfig


class RedisManager:
    """
    Redis connection and session manager for caching and session storage.
    Handles JWT isessions, buoy data caching, and general caching needs.
    """

    def __init__(self, settings: BaseConfig, logger: logging.Logger):
        self.settings = settings
        self.redis_url = settings.redis_url
        self._client: Optional[Redis] = None
        self.logger = logger

    def _create_client(self) -> Redis:
        """Create Redis client with connection pooling."""
        return redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=self.settings.redis_max_connections,
            retry_on_timeout=True,
            socket_connect_timeout=self.settings.redis_connect_timeout,
            socket_timeout=self.settings.redis_socket_timeout,
        )

    @property
    def client(self) -> Redis:
        """Get Redis client, creating if necessary."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    async def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            await self.client.ping()
            return True
        except Exception as e:
            self.logger.error(f"Redis health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connections."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ===== SESSION MANAGEMENT (for JWT) =====

    async def set_session(
        self, session_id: str, data: Dict[str, Any], ttl: int
    ) -> bool:
        """Store JWT session data."""
        try:
            session_key = f"session:{session_id}"
            await self.client.setex(session_key, ttl, json.dumps(data))
            return True
        except Exception as e:
            self.logger.error(f"Failed to set session {session_id}: {e}")
            return False

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve JWT session data."""
        try:
            session_key = f"session:{session_id}"
            data = await self.client.get(session_key)
            return json.loads(data) if data else None
        except Exception as e:
            self.logger.error(f"Failed to get session {session_id}: {e}")
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete JWT session (logout)."""
        try:
            session_key = f"session:{session_id}"
            result = await self.client.delete(session_key)
            return result > 0
        except Exception as e:
            self.logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    async def extend_session(self, session_id: str, ttl: int) -> bool:
        """Extend session TTL."""
        try:
            session_key = f"session:{session_id}"
            return await self.client.expire(session_key, ttl)
        except Exception as e:
            self.logger.error(f"Failed to extend session {session_id}: {e}")
            return False

    # ===== GENERAL CACHING =====

    async def set_cache(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """General purpose cache setter."""
        try:
            serialized_value = json.dumps(value)
            if ttl:
                await self.client.setex(key, ttl, serialized_value)
            else:
                await self.client.set(key, serialized_value)
            return True
        except Exception as e:
            self.logger.error(f"Failed to set cache key {key}: {e}")
            return False

    async def get_cache(self, key: str) -> Optional[Any]:
        """General purpose cache getter."""
        try:
            data = await self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            self.logger.error(f"Failed to get cache key {key}: {e}")
            return None

    async def delete_cache(self, key: str) -> bool:
        """Delete cache key."""
        try:
            result = await self.client.delete(key)
            return result > 0
        except Exception as e:
            self.logger.error(f"Failed to delete cache key {key}: {e}")
            return False

    @asynccontextmanager
    async def pipeline(self):
        """Context manager for Redis pipeline operations."""
        pipe = self.client.pipeline()
        try:
            yield pipe
            await pipe.execute()
        except Exception as e:
            self.logger.error(f"Pipeline operation failed: {e}")
            raise
