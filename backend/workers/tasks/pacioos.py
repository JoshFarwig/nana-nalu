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
    get_enabled_regions_for_model,
)
from utils.region import Region

logger = logging.getLogger(__name__)


# =========================
# PARENT TASK - TIDE DISPATCHER
# =========================


@shared_task
def fetch_all_tide_forecasts():
    """
    Parent dispatcher task for PacIOOS Tide model.

    Spawns one child task per enabled region that has tide configuration.
    Runs weekly since tidal predictions are pre-computed through Dec 2026.
    We only need fresh data for Redis TTL maintenance.
    """
    regions = get_enabled_regions_for_model(PacIOOSModel.TIDE)

    if not regions:
        logger.warning("No enabled regions with tide configuration")
        return {"regions_dispatched": 0}

    job = group(
        fetch_tide.si(r.value)  # type: ignore
        for r in regions  # type: ignore
    )

    result = job.apply_async()

    logger.info(
        f"Dispatched {len(regions)} fetch tasks",
        extra={
            "regions": [r.value for r in regions],
            "group_id": result.id,
        },
    )

    return {
        "regions_dispatched": len(regions),
        "regions": [r.value for r in regions],
        "group_id": result.id,
    }


# =========================
# CHILD TASK - TIDE FETCH
# =========================


@shared_task(bind=True, max_retries=3)
def fetch_tide(self, region_str: str):
    """
    Fetch PacIOOS Tide forecast data for a specific region.

    Downloads NetCDF subset via ERDDAP GridDAP, then extracts sea surface height (tide).
    Stores results in Redis with key pattern: forecast:pacioos:tide:{region}:{spot_id}

    Note: Only fetches sea surface height (ssh). Tidal currents (u/v) not included.
    For comprehensive ocean currents, use ROMS model instead.

    Args:
        region_str: Region string value (e.g., "maui")
    """
    db_manager = get_db_manager()
    redis_manager = get_redis_manager()
    http_manager = get_http_manager()

    region = Region(region_str)
    config = get_pacioos_config(region, PacIOOSModel.TIDE)

    logger.info(
        f"Starting fetch for {region_str}",
        extra={
            "region": region_str,
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
                    f"No forecasts extracted for {region_str}",
                    extra={"region": region_str},
                )
                return {"status": "no_spots", "region": region_str}

            logger.info(
                f"[PacIOOS:Tide] Extracted forecasts for {len(forecasts)} spots",
                extra={
                    "region": region_str,
                    "spot_ids": list(forecasts.keys()),
                },
            )

            # TTL: 8 days (weekly refresh + buffer)
            ttl = timedelta(days=config.forecast_horizon_days + 1)

            with redis_manager.client.pipeline() as pipe:
                for spot_id, provider_forecast in forecasts.items():
                    key = f"forecast:pacioos:tide:{region_str}:{spot_id}"
                    pipe.setex(key, ttl, provider_forecast.to_redis_json())

                # track last successful fetch
                last_run_key = f"forecast:pacioos:tide:{region_str}:last_run"
                pipe.set(last_run_key, datetime.now(timezone.utc).isoformat())

                result = pipe.execute()

                logger.info(
                    "Redis pipeline executed",
                    extra={
                        "region": region_str,
                        "commands_executed": len(result),
                        "last_run_key": last_run_key,
                    },
                )

            logger.info(
                f"Successfully fetched for {region_str}",
                extra={
                    "region": region_str,
                    "spots_processed": len(forecasts),
                },
            )

            return {
                "status": "success",
                "region": region_str,
                "spots_processed": len(forecasts),
            }

    except Exception as e:
        logger.exception(
            f"Error fetching for {region_str}",
            extra={
                "region": region_str,
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
