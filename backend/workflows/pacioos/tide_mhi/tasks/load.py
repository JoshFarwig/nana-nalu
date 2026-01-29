"""
Load transformed forecast data to Redis.

Stores transformed forecasts to Redis with TTL using pipeline for efficiency.
Also manages the last_run timestamp for idempotency checking.
"""

from datetime import timedelta

from prefect import task, get_run_logger

from workflows.resources import get_resources
from services.forecast.forecast_schema import ProviderForecast


@task(name="tide-mhi-load", retries=2, retry_delay_seconds=10)
async def load(
    forecasts: dict[int, ProviderForecast],
    region: str,
    run_id: str,
    ttl_hours: int = 168,  # 7 days - matches weekly refresh cycle
) -> int:
    """
    Load forecast data to Redis with TTL.

    Key pattern: forecast:pacioos:tide:{region}:{spot_id}
    Also updates: forecast:pacioos:tide:{region}:last_run

    Args:
        forecasts: Dictionary mapping spot_id -> ProviderForecast
        region: Region string (e.g., "maui")
        run_id: ISO format datetime string for this run
        ttl_hours: Time-to-live for forecast data (default 168h / 7 days)

    Returns:
        Number of forecasts loaded
    """
    logger = get_run_logger()
    resources = await get_resources()
    redis_client = resources.redis.client

    if not forecasts:
        logger.warning("No forecasts to load")
        return 0

    last_run_key = f"forecast:pacioos:tide:{region}:last_run"

    async with redis_client.pipeline() as pipe:
        for spot_id, provider_forecast in forecasts.items():
            key = f"forecast:pacioos:tide:{region}:{spot_id}"
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


async def get_last_run_time(region: str) -> str | None:
    """
    Get the last successful run timestamp from Redis.

    Args:
        region: Region string (e.g., "maui")

    Returns:
        ISO format datetime string or None if no previous run
    """
    resources = await get_resources()
    redis_client = resources.redis.client
    key = f"forecast:pacioos:tide:{region}:last_run"
    return await redis_client.get(key)
