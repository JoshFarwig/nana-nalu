"""
Load transformed forecast data to Redis.

Stores transformed forecasts to Redis with TTL using pipeline for efficiency.
Also manages the last_run timestamp for idempotency checking.
"""

from datetime import timedelta

from prefect import task, get_run_logger
from redis.asyncio import Redis

from services.forecast.forecast_schema import ProviderForecast


@task(name="nwps-load", retries=2, retry_delay_seconds=10)
async def load(
    forecasts: dict[int, ProviderForecast],
    redis_client: Redis,
    region: str,
    run_id: str,
    ttl_hours: int = 14,
) -> int:
    """
    Load forecast data to Redis with TTL.

    Key pattern: forecast:nomads:nwps:{region}:{spot_id}
    Also updates: forecast:nomads:nwps:{region}:last_run

    Args:
        forecasts: Dictionary mapping spot_id -> ProviderForecast
        redis_client: Async Redis client
        region: Region string (e.g., "maui")
        run_id: ISO format datetime string for this run
        ttl_hours: Time-to-live for forecast data (default 14h)

    Returns:
        Number of forecasts loaded
    """
    logger = get_run_logger()

    if not forecasts:
        logger.warning("No forecasts to load")
        return 0

    last_run_key = f"forecast:nomads:nwps:{region}:last_run"

    async with redis_client.pipeline() as pipe:
        for spot_id, provider_forecast in forecasts.items():
            key = f"forecast:nomads:nwps:{region}:{spot_id}"
            await pipe.setex(
                key,
                timedelta(hours=ttl_hours),
                provider_forecast.to_redis_json(),
            )

        # mark run as processed
        await pipe.set(last_run_key, run_id)
        await pipe.execute()

    logger.info(
        f"Loaded {len(forecasts)} forecasts to Redis",
        extra={
            "region": region,
            "run_id": run_id,
            "spot_ids": list(forecasts.keys()),
            "ttl_hours": ttl_hours,
        },
    )

    return len(forecasts)


async def get_last_run_time(redis_client: Redis, region: str) -> str | None:
    """
    Get the last successful run timestamp from Redis.

    Args:
        redis_client: Async Redis client
        region: Region string (e.g., "maui")

    Returns:
        ISO format datetime string or None if no previous run
    """
    key = f"forecast:nomads:nwps:{region}:last_run"
    return await redis_client.get(key)
