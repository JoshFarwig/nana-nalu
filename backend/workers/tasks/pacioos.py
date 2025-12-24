import logging
from datetime import timedelta, timezone, datetime

from celery import shared_task, group

from workers.signals import (
    get_db_manager,
    get_redis_manager,
    get_http_manager,
)

from repositories.surf_spot_repository import SyncSurfSpotRepository
from services.forecast.providers.pacioos.provider import PacIOOSProvider
from services.forecast.providers.pacioos.config import (
    PacIOOSModel,
    get_pacioos_config,
    get_enabled_locations_for_model,
)
from utils.location import Location

logger = logging.getLogger(__name__)


# =========================
# PARENT TASK - TIDE DISPATCHER
# =========================


@shared_task
def fetch_all_tide_forecasts():
    """
    Parent dispatcher task for PacIOOS Tide model.

    Spawns one child task per enabled location that has tide configuration.
    Runs weekly since tidal predictions are pre-computed through Dec 2026.
    We only need fresh data for Redis TTL maintenance.
    """
    locations = get_enabled_locations_for_model(PacIOOSModel.TIDE)

    if not locations:
        logger.warning("No enabled locations with tide configuration")
        return {"locations_dispatched": 0}

    job = group(
        fetch_tide.si(loc.value)  # type: ignore
        for loc in locations  # type: ignore
    )

    result = job.apply_async()

    logger.info(
        f"Dispatched {len(locations)} fetch tasks",
        extra={
            "locations": [loc.value for loc in locations],
            "group_id": result.id,
        },
    )

    return {
        "locations_dispatched": len(locations),
        "locations": [loc.value for loc in locations],
        "group_id": result.id,
    }


# =========================
# CHILD TASK - TIDE FETCH
# =========================


@shared_task(bind=True, max_retries=3)
def fetch_tide(self, loc: str):
    """
    Fetch PacIOOS Tide forecast data for a specific location.

    Downloads NetCDF subset via ERDDAP GridDAP, then extracts sea surface height (tide).
    Stores results in Redis with key pattern: forecast:pacioos:tide:{location}:{spot_id}

    Note: Only fetches sea surface height (ssh). Tidal currents (u/v) not included.
    For comprehensive ocean currents, use ROMS model instead.

    Args:
        loc: Location string value (e.g., "maui")
    """
    db_manager = get_db_manager()
    redis_manager = get_redis_manager()
    http_manager = get_http_manager()

    location = Location(loc)
    config = get_pacioos_config(location, PacIOOSModel.TIDE)

    logger.info(
        f"Starting fetch for {loc}",
        extra={
            "location": loc,
            "dataset_id": config.dataset_id,
            "griddap_url": config.griddap_url,
        },
    )

    try:
        with db_manager.explicit_commit_session() as session:
            surf_spot_repo = SyncSurfSpotRepository(session)
            provider = PacIOOSProvider(config, http_manager, surf_spot_repo)

            # download NetCDF subset via GridDAP
            file_path = provider.download_file()

            # extract forecasts from downloaded file
            forecasts = provider.extract_forecasts(file_path)

            if not forecasts:
                logger.warning(
                    f"No forecasts extracted for {loc}",
                    extra={"location": loc},
                )
                return {"status": "no_spots", "location": loc}

            logger.info(
                f"[PacIOOS:Tide] Extracted forecasts for {len(forecasts)} spots",
                extra={
                    "location": loc,
                    "spot_ids": list(forecasts.keys()),
                },
            )

            # TTL: 8 days (weekly refresh + buffer)
            ttl = timedelta(days=config.forecast_horizon_days + 1)

            with redis_manager.client.pipeline() as pipe:
                for spot_id, provider_forecast in forecasts.items():
                    key = f"forecast:pacioos:tide:{loc}:{spot_id}"
                    pipe.setex(key, ttl, provider_forecast.to_redis_json())

                # track last successful fetch
                last_run_key = f"forecast:pacioos:tide:{loc}:last_run"
                pipe.set(last_run_key, datetime.now(timezone.utc).isoformat())

                result = pipe.execute()

                logger.info(
                    "Redis pipeline executed",
                    extra={
                        "location": loc,
                        "commands_executed": len(result),
                        "last_run_key": last_run_key,
                    },
                )

            logger.info(
                f"Successfully fetched for {loc}",
                extra={
                    "location": loc,
                    "spots_processed": len(forecasts),
                },
            )

            return {
                "status": "success",
                "location": loc,
                "spots_processed": len(forecasts),
            }

    except Exception as e:
        logger.exception(
            f"Error fetching for {loc}",
            extra={
                "location": loc,
                "error": str(e),
                "attempt": self.request.retries + 1,
                "max_retries": self.max_retries,
            },
        )

        # retry with 10 minute backoff for transient errors
        if self.request.retries < self.max_retries:
            retry_countdown = 600  # 10 minutes
            raise self.retry(exc=e, countdown=retry_countdown)
        raise
