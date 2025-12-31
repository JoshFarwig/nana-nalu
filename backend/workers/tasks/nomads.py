import logging
from datetime import timedelta, timezone, datetime
from pathlib import Path
from celery import shared_task, group
from httpx import HTTPStatusError, NetworkError, TimeoutException

from workers.signals import (
    get_db_manager,
    get_redis_manager,
    get_http_manager,
)

from repositories.surf_spot_repository import SyncSurfSpotRepository

from services.forecast.providers.nomads.provider import NOMADSProvider
from services.forecast.providers.nomads.config import (
    get_enabled_regions_for_model,
    get_nomads_config,
    NOMADSModel,
)
from services.forecast.providers.nomads.availability import NOMADSAvailabilityChecker
from utils.region import Region

logger = logging.getLogger(__name__)


# =======================
# HELPER FUNCTIONS
# =======================


def _remove_grib2_file(file_path: Path):
    for idx in file_path.parent.glob(f"{file_path.name}.*.idx"):
        idx.unlink()
    file_path.unlink()


# =======================
# CUSTOM EXCEPTIONS
# =======================


class NoNewRunAvailable(Exception):
    """Raised when NOMADS has no new run available yet (not an error, just early)"""

    pass


# =========================
# PARENT TASK - NWPS DISPATCHER
# =========================


@shared_task
def fetch_all_nwps_forecasts():
    """
    Parent dispatcher task for NOMADS NWPS model.

    Spawns one child task per enabled region to check availability and fetch if new data exists.
    Gracefully skips regions that don't have NWPS configuration.

    Designed for periodic polling - frequency depends on WFO run schedule:
    - HFO (Hawaii): 2x daily polls for unpredictable 2x daily runs (e.g., 7:00 & 17:00 UTC)
    - Other WFOs: Adjust beat schedule to match their analysis time intervals (3hr, 6hr, etc.)

    Retry logic is hardcoded: 3 retries × 1hr for "no data", 3 retries × 5min for network errors.
    """
    regions = get_enabled_regions_for_model(NOMADSModel.NWPS)

    if not regions:
        logger.warning("No enabled regions with NWPS configuration")
        return {"regions_dispatched": 0}

    job = group(
        fetch_nwps.si(r.value)  # type: ignore
        for r in regions
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
# CHILD TASK - NWPS FETCH
# =========================


@shared_task(bind=True, max_retries=3)
def fetch_nwps(self, region_str: str):
    """
    Fetch NOMADS NWPS forecast data for a specific region.

    Polls NOMADS for new NWPS runs, downloads GRIB2 files, and extracts wave/wind forecasts.
    Stores results in Redis with key pattern: forecast:nomads:nwps:{region}:{spot_id}

    Handles unpredictable NWPS run schedules by:
    1. Checking what's actually available on NOMADS (via HEAD requests)
    2. Comparing to what we already have cached in Redis
    3. Fetching only if there's new data and it's not too old

    Retry strategy (intelligent based on failure type):
    - No new run available: Retry 3x with 1hr intervals (model likely still running)
    - Network/download errors: Retry 3x with 5min intervals (transient failures)
    - Already current or too old: Exit immediately, no retry needed

    Args:
        region_str: Region string value (e.g., "maui")
    """

    db_manager = get_db_manager()
    redis_manager = get_redis_manager()
    http_manager = get_http_manager()

    region = Region(region_str)
    config = get_nomads_config(region, NOMADSModel.NWPS)

    logger.info(
        f"Starting fetch for {region_str}",
        extra={
            "region": region_str,
            "wfo": config.wfo.value,
            "cg": config.cg,
        },
    )

    # get the last run timestamp from Redis to optimize search window
    # key pattern: forecast:{provider}:{model}:{region}:last_run
    last_run_key = f"forecast:nomads:nwps:{region_str}:last_run"
    last_run_id = redis_manager.client.get(last_run_key)

    # parse last run time if it exists, otherwise None
    # last_run_id is stored as ISO format datetime string (e.g., "2025-01-26T06:00:00+00:00")
    last_run_time = datetime.fromisoformat(last_run_id) if last_run_id else None  # type: ignore

    # check what's available (searches back to last_run_time if provided, else 24h)
    checker = NOMADSAvailabilityChecker(config, http_manager)
    latest_run = checker.get_latest_available_run(last_run_time=last_run_time)

    if not latest_run:
        # model likely still running - retry with 1hr backoff
        if self.request.retries < self.max_retries:
            retry_countdown = 3600  # 1 hour in seconds
            logger.info(
                f"No new run available for {region_str}, will retry in {retry_countdown // 60}min",
                extra={
                    "region": region_str,
                    "attempt": self.request.retries + 1,
                    "max_retries": self.max_retries,
                    "retry_in_seconds": retry_countdown,
                },
            )
            raise self.retry(
                exc=NoNewRunAvailable(f"No new run for {region_str}"),
                countdown=retry_countdown,
            )
        else:
            logger.warning(
                f"No new runs found for {region_str} after {self.max_retries} retries, giving up until next beat",
                extra={"region": region_str, "attempts": self.max_retries + 1},
            )
            return {"status": "no_data_available", "retries_exhausted": True}

    forecast_date, analysis_time = latest_run

    # create run_id as ISO format datetime string for storage in Redis
    run_datetime = datetime.combine(forecast_date, analysis_time, tzinfo=timezone.utc)
    run_id = run_datetime.isoformat()

    # check if we already have this run (idempotency)
    if last_run_id == run_id:
        logger.info(f"Already have latest run {run_id}, skipping")
        return {"status": "already_current", "run": run_id}

    # check if forecast is too old
    age_hours = (datetime.now(timezone.utc) - run_datetime).total_seconds() / 3600

    if age_hours > config.max_forecast_age_hours:
        logger.warning(
            f"Latest run {run_id} is {age_hours:.1f}h old (max: {config.max_forecast_age_hours}h), skipping",
            extra={
                "run_id": run_id,
                "age_hours": age_hours,
                "max_age": config.max_forecast_age_hours,
            },
        )
        return {"status": "forecast_too_old", "run": run_id, "age_hours": age_hours}

    # new run available - fetch it!
    logger.info(f"New run available: {run_id}, fetching...")

    with db_manager.explicit_commit_session() as session:
        surf_spot_repo = SyncSurfSpotRepository(session)
        provider = NOMADSProvider(config, http_manager, surf_spot_repo)

        try:
            # download and extract (returns ProviderForecast objects ready for Redis)
            file_path = provider.download_file(analysis_time, forecast_date)
            forecasts = provider.extract_forecasts(file_path)

            logger.info(
                f"Extracted forecasts for {len(forecasts)} spots",
                extra={
                    "region": region_str,
                    "spot_ids": list(forecasts.keys()),
                    "run_id": run_id,
                },
            )

            # store in Redis with new key pattern: forecast:{provider}:{model}:{region}:{spot_id}
            with redis_manager.client.pipeline() as pipe:
                for spot_id, provider_forecast in forecasts.items():
                    key = f"forecast:nomads:nwps:{region_str}:{spot_id}"
                    pipe.setex(
                        key, timedelta(hours=14), provider_forecast.to_redis_json()
                    )

                # mark as processed
                pipe.set(last_run_key, run_id)
                result = pipe.execute()

                logger.info(
                    "Redis pipeline executed",
                    extra={
                        "region": region_str,
                        "commands_executed": len(result),
                        "last_run_key": last_run_key,
                    },
                )

            # cleanup grib2 file
            _remove_grib2_file(file_path)

            logger.info(
                f"Successfully fetched run {run_id} for {region_str}",
                extra={
                    "region": region_str,
                    "run_id": run_id,
                    "spots_processed": len(forecasts),
                },
            )

            return {
                "status": "success",
                "run": run_id,
                "spots_processed": len(forecasts),
            }

        except (HTTPStatusError, NetworkError, TimeoutException) as e:
            # network/download errors - retry with shorter 5min backoff
            if self.request.retries < self.max_retries:
                download_retry_countdown = 300  # 5 minutes for transient errors
                logger.warning(
                    f"Forecast extraction for {region_str} at {run_id}, will retry in {download_retry_countdown // 60}min",
                    extra={
                        "region": region_str,
                        "run_id": run_id,
                        "retry_in_seconds": download_retry_countdown,
                        "attempt": self.request.retries + 1,
                        "max_retries": self.max_retries,
                        "error": str(e),
                    },
                )
                raise self.retry(exc=e, countdown=download_retry_countdown)
            else:
                logger.error(
                    f"Forecast extraction for {region_str} at {run_id} after {self.max_retries} retries",
                    extra={
                        "region": region_str,
                        "run_id": run_id,
                        "attempts": self.max_retries + 1,
                        "error": str(e),
                    },
                )
                raise

        except Exception as e:
            logger.exception(
                f"Unexpected error extracting forecast for {region_str} at {run_id}",
                extra={
                    "region": region_str,
                    "run_id": run_id,
                    "error": str(e),
                },
            )
            raise
