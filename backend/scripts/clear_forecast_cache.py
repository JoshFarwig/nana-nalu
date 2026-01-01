#!/usr/bin/env python3
"""
Clear all forecast data from Redis cache.

Run this during deployment when forecast schema changes to prevent
deserialization errors from old cached data.

Usage:
    python scripts/clear_forecast_cache.py
"""

import sys
import logging
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.redis import SyncRedisManager
from core.config import load_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_forecast_cache():
    """Delete all Redis keys matching forecast:* pattern."""
    settings = load_settings("worker")
    redis_url = settings.redis.get_cache_url()
    redis_manager = SyncRedisManager(settings.redis, redis_url)

    pattern = "forecast:*"
    cursor = 0
    total_deleted = 0

    logger.info(f"Scanning for keys matching pattern: {pattern}")

    # Use SCAN to avoid blocking Redis
    while True:
        cursor, keys = redis_manager.client.scan(cursor, match=pattern, count=100)

        if keys:
            deleted = redis_manager.client.delete(*keys)
            total_deleted += deleted
            logger.info(f"Deleted {deleted} keys (batch), total: {total_deleted}")

        if cursor == 0:
            break

    logger.info(f"Cache clear complete. Total keys deleted: {total_deleted}")
    redis_manager.close()

    return total_deleted


if __name__ == "__main__":
    try:
        count = clear_forecast_cache()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}", exc_info=True)
        sys.exit(1)
