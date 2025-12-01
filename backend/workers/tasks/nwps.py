import logging
import json
from datetime import timedelta, timezone, datetime

from celery import shared_task, group
from httpx import HTTPStatusError, NetworkError, TimeoutException

from workers.signals import (
    get_db_manager,
    get_redis_manager,
    get_http_manager,
    get_worker_locations,
)

from repositories.surf_spot_repository import SyncSurfSpotRepository
from services.forecast.providers.nwps.provider import NWPSProvider
from services.forecast.providers.nwps.config import get_nwps_config
from services.forecast.providers.nwps.availability import NWPSAvailabilityChecker
from utils.location import Location

logger = logging.getLogger(__name__)


# =======================
# CUSTOM EXCEPTIONS
# =======================


class NoNewRunAvailable(Exception):
    """Raised when NOMADS has no new NWPS run available yet (not an error, just early)"""

    pass


# =========================
# PARENT TASK - DISPATCHER
# =========================


@shared_task
def fetch_all_nwps_forecasts():
    """
    Parent dispatcher task that checks all enabled locations for new NWPS data.

    Spawns one child task per location to check availability and fetch if new data exists.
    Gracefully skips locations that don't have NWPS configuration.

    Designed for periodic polling - frequency depends on WFO run schedule:
    - HFO (Hawaii): 2x daily polls for unpredictable 2x daily runs (e.g., 7:00 & 17:00 UTC)
    - Other WFOs: Adjust beat schedule to match their analysis time intervals (3hr, 6hr, etc.)

    Retry logic is hardcoded: 3 retries × 1hr for "no data", 3 retries × 5min for network errors.
    """
    from services.forecast.providers.nwps.provider import NWPSProvider

    locations = get_worker_locations()

    if not locations:
        logger.warning("[NWPS] No enabled locations found")
        return {"locations_dispatched": 0}

    # Filter to only locations supported by NWPS
    supported_locations = [
        loc for loc in locations if NWPSProvider.supports_location(loc)
    ]

    if not supported_locations:
        logger.warning(
            "[NWPS] No NWPS configurations found for enabled locations",
            extra={"enabled_locations": [loc.value for loc in locations]},
        )
        return {"locations_dispatched": 0, "locations_skipped": len(locations)}

    # Log skipped locations
    skipped = set(locations) - set(supported_locations)
    if skipped:
        logger.info(
            "[NWPS] Skipping locations without NWPS configuration",
            extra={"skipped_locations": [loc.value for loc in skipped]},
        )

    job = group(
        check_and_fetch_if_new.si(loc)  # type: ignore
        for loc in supported_locations
    )

    result = job.apply_async()

    logger.info(
        f"[NWPS] Dispatched {len(supported_locations)} polling tasks",
        extra={
            "locations": [loc.value for loc in supported_locations],
            "group_id": result.id,
        },
    )

    return {
        "locations_dispatched": len(supported_locations),
        "locations_skipped": len(skipped),
        "locations": [loc.value for loc in supported_locations],
        "group_id": result.id,
    }


# =========================
# CHILD TASK - PER LOCATION
# =========================


@shared_task(bind=True, max_retries=3)
def check_and_fetch_if_new(self, loc: Location):
    """
    Poll NOMADS for new NWPS data and fetch if available.

    Handles unpredictable NWPS run schedules by:
    1. Checking what's actually available on NOMADS (via HEAD requests)
    2. Comparing to what we already have cached in Redis
    3. Fetching only if there's new data and it's not too old

    Retry strategy (intelligent based on failure type):
    - No new run available: Retry 3x with 1hr intervals (model likely still running)
    - Network/download errors: Retry 3x with 5min intervals (transient failures)
    - Already current or too old: Exit immediately, no retry needed
    """
    db_manager = get_db_manager()
    redis_manager = get_redis_manager()
    http_manager = get_http_manager()

    config = get_nwps_config(loc)

    # get the last run timestamp from Redis to optimize search window
    last_run_key = f"nwps:{loc.value}:last_run"
    last_run_id = redis_manager.client.get(last_run_key)

    # parse last run time if it exists, otherwise None
    # last_run_id is stored as ISO format datetime string (e.g., "2025-01-26T06:00:00+00:00")
    last_run_time = datetime.fromisoformat(last_run_id) if last_run_id else None  # type: ignore

    # check what's available (searches back to last_run_time if provided, else 24h)
    checker = NWPSAvailabilityChecker(config, http_manager)
    latest_run = checker.get_latest_available_run(last_run_time=last_run_time)

    if not latest_run:
        # model likely still running - retry with 1hr backoff
        if self.request.retries < self.max_retries:
            retry_countdown = 3600  # 1 hour in seconds
            logger.info(
                f"[NWPS] No new run available for {loc.value}, will retry in {retry_countdown // 60}min",
                extra={
                    "location": loc.value,
                    "attempt": self.request.retries + 1,
                    "max_retries": self.max_retries,
                    "retry_in_seconds": retry_countdown,
                },
            )
            raise self.retry(
                exc=NoNewRunAvailable(f"[NWPS] No new run for {loc.value}"),
                countdown=retry_countdown,
            )
        else:
            logger.warning(
                f"[NWPS] No new runs found for {loc.value} after {self.max_retries} retries, giving up until next beat",
                extra={"location": loc.value, "attempts": self.max_retries + 1},
            )
            return {"status": "no_data_available", "retries_exhausted": True}

    forecast_date, analysis_time = latest_run

    # create run_id as ISO format datetime string for storage in Redis
    run_datetime = datetime.combine(forecast_date, analysis_time)
    run_id = run_datetime.isoformat()

    # check if we already have this run (idempotency)
    if last_run_id == run_id:
        logger.info(f"[NWPS] Already have latest run {run_id}, skipping")
        return {"status": "already_current", "run": run_id}

    # check if forecast is too old
    age_hours = (datetime.now(timezone.utc) - run_datetime).total_seconds() / 3600

    if age_hours > config.max_forecast_age_hours:
        logger.warning(
            f"[NWPS] Latest run {run_id} is {age_hours:.1f}h old (max: {config.max_forecast_age_hours}h), skipping",
            extra={
                "run_id": run_id,
                "age_hours": age_hours,
                "max_age": config.max_forecast_age_hours,
            },
        )
        return {"status": "forecast_too_old", "run": run_id, "age_hours": age_hours}

    # new run available - fetch it!
    logger.info(f"[NWPS] New run available: {run_id}, fetching...")

    with db_manager.explicit_commit_session() as session:
        surf_spot_repo = SyncSurfSpotRepository(session)
        provider = NWPSProvider(config, http_manager, surf_spot_repo)

        try:
            # download and extract
            file_path = provider.download_file(analysis_time, forecast_date)
            forecasts = provider.extract_forecasts(file_path)

            # store in Redis
            with redis_manager.client.pipeline() as pipe:
                for spot_id, spot_data in forecasts.items():
                    key = f"forecast:nwps:{loc.value}:{spot_id}"
                    pipe.setex(key, timedelta(hours=14), json.dumps(spot_data))

                # mark as processed
                pipe.set(last_run_key, run_id)
                pipe.execute()

            # cleanup file
            file_path.unlink(missing_ok=True)

            logger.info(
                f"[NWPS] Successfully fetched run {run_id} for {loc.value}",
                extra={
                    "location": loc.value,
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
                    f"[NWPS] Forecast extraction for {loc.value} at {run_id}, will retry in {download_retry_countdown // 60}min",
                    extra={
                        "location": loc.value,
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
                    f"[NWPS] Forecast extraction for {loc.value} at {run_id} after {self.max_retries} retries",
                    extra={
                        "location": loc.value,
                        "run_id": run_id,
                        "attempts": self.max_retries + 1,
                        "error": str(e),
                    },
                )
                raise

        except Exception as e:
            logger.exception(
                f"[NWPS] Unexpected error extracting forecast for {loc.value} at {run_id}",
                extra={
                    "location": loc.value,
                    "run_id": run_id,
                    "error": str(e),
                },
            )
            raise
