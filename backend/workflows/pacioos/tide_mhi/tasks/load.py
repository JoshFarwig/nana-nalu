from datetime import timedelta

from prefect import task, get_run_logger

from workflows.resources import get_resources
from services.forecast.forecast_schema import ProviderForecast


@task(name="tide-mhi-load", retries=2, retry_delay_seconds=10)
def load(
    forecasts: dict[int, ProviderForecast],
    provider: str,
    model: str,
    region: str,
    run_id: str,
    ttl_hours: int = 168,  # 7 days - matches weekly refresh cycle
) -> int:
    """
    Load forecast data to Redis with TTL.

    Key pattern: forecast:{provider}:{model}:{region}:{spot_id}
    Also updates: forecast:{provider}:{model}:{region}:last_run

    Args:
        forecasts: Dictionary mapping spot_id -> ProviderForecast
        provider: Provider name (e.g., "pacioos")
        model: Model name (e.g., "tide_mhi")
        region: Region string (e.g., "maui")
        run_id: ISO format datetime string for this run
        ttl_hours: Time-to-live for forecast data (default 168h / 7 days)

    Returns:
        Number of forecasts loaded
    """
    logger = get_run_logger()
    resources = get_resources()
    redis_client = resources.redis.client

    if not forecasts:
        logger.warning("No forecasts to load")
        return 0

    last_run_key = f"forecast:{provider}:{model}:{region}:last_run"

    with redis_client.pipeline() as pipe:
        for spot_id, provider_forecast in forecasts.items():
            key = f"forecast:{provider}:{model}:{region}:{spot_id}"
            pipe.setex(
                key,
                timedelta(hours=ttl_hours),
                provider_forecast.to_redis_json(),
            )

        # mark run as processed
        pipe.set(last_run_key, run_id)
        pipe.execute()

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


def get_last_run_time(provider: str, model: str, region: str) -> str | None:
    """
    Get the last successful run timestamp from Redis.

    Args:
        provider: Provider name (e.g., "pacioos")
        model: Model name (e.g., "tide_mhi")
        region: Region string (e.g., "maui")

    Returns:
        ISO format datetime string or None if no previous run
    """
    resources = get_resources()
    redis_client = resources.redis.client
    key = f"forecast:{provider}:{model}:{region}:last_run"
    return redis_client.get(key)  # type: ignore
