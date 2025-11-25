"""
NWPS (NOAA Wave Prediction System) forecast tasks.

Architecture:
- Parent task: Dispatches island-specific downloads for a given analysis time
- Child task: Downloads GRIB2 for one island, handles 404s with adaptive retry

Each island's NWPS grid has:
- model_analysis_times: When NOAA runs the model (e.g., 00z, 12z)
- model_long_wait_time: Expected processing time (e.g., 6.5 hours after analysis start)
- model_short_wait_time: Retry interval if GRIB2 not ready (e.g., 10 minutes)

Workflow:
1. Beat scheduler triggers at analysis_time + long_wait_time
2. Parent task groups islands with same analysis time
3. Child tasks download GRIB2 per island, retry with short_wait_time on 404
"""

import logging
import json
from datetime import timedelta, timezone, time

from celery import shared_task, group
from httpx import HTTPStatusError, NetworkError, TimeoutException

from workers.signals import (
    get_db_manager,
    get_redis_manager,
    get_http_manager,
)

from repositories.surf_spot_repository import SyncSurfSpotRepository
from services.forecast.providers.nwps.provider import NWPSProvider
from services.forecast.providers.nwps.config import (
    get_nwps_config,
    get_locations_for_analysis_time,
)
from utils.location import Location

logger = logging.getLogger(__name__)


# =======================
# EXCEPTION CLASSES
# =======================


class NWPSGRIB2NotReadyError(Exception):
    """Raised when GRIB2 file returns 404 (not ready yet on NOMADS)."""

    pass


# =========================
# PARENT TASK - DISPATCHER
# =======================


@shared_task
def fetch_nwps_forecasts_for_analysis_time(analysis_hour: int):
    """
    Parent task: Dispatch NWPS downloads for all configured locations with this analysis time.

    Called by beat scheduler at analysis_time + long_wait_time.
    Uses group() with .si() to fan out to independent child tasks.

    Args:
        analysis_hour: UTC hour (0-23) of the model analysis time

    Returns:
        dict: Summary with locations dispatched and task group ID
    """
    analysis_time = time(analysis_hour, 0, tzinfo=timezone.utc)
    locations = get_locations_for_analysis_time(analysis_time)

    if not locations:
        logger.warning(
            f"[NWPS] No location configurations found for analysis time: {analysis_time.strftime('%H:%M %Z')}",
            extra={"analysis_time": analysis_time.isoformat()},
        )
        return {"locations_dispatched": 0}

    job = group(
        add_nwps_forecast.si(loc, analysis_hour)  # type: ignore[misc]
        for loc, _ in locations
    )

    result = job.apply_async()

    logger.info(
        f"[NWPS] Dispatched {len(locations)} tasks for {analysis_hour:02d}z",
        extra={
            "locations": [loc.value for loc, _ in locations],
            "group_id": result.id,
        },
    )

    return {
        "locations_dispatched": len(locations),
        "locations": [loc.value for loc, _ in locations],
        "group_id": result.id,
    }


# =======================
# Child task:
# =======================


@shared_task(
    bind=True,
    max_retries=5,
    time_limit=300,
    soft_time_limit=270,
)
def add_nwps_forecast(
    self,
    loc: Location,
    analysis_hour: int,
):
    db_manager = get_db_manager()
    redis_manager = get_redis_manager()
    http_manager = get_http_manager()
    config = get_nwps_config(loc)

    valid_times = list(config.model_analysis_times.values())
    analysis_time = time(analysis_hour, 0, tzinfo=timezone.utc)
    retry_countdown = int(config.model_short_wait_time.total_seconds())

    if analysis_time not in valid_times:
        raise ValueError(
            f"Invalid analysis time {analysis_hour:02d}z for {loc.value}. "
            f"Valid times for {loc.value}: {[t.hour for t in valid_times]}"
        )

    logger.info(
        f"[NWPS] Starting GRIB2 forecast data download for {loc.value} — {analysis_hour:02d}z",
        extra={
            "location": loc.value,
            "analysis_hour": analysis_hour,
            "retry_count": self.max_retries,
        },
    )

    with (
        db_manager.explicit_commit_session() as session,
        redis_manager.client.pipeline() as pipe,
    ):
        surf_spot_repo = SyncSurfSpotRepository(session)
        provider = NWPSProvider(config, http_manager, surf_spot_repo)

        try:
            file_path = provider.download_file(analysis_time)
            forecasts = provider.extract_forecasts(file_path)

            for spot_id, spot_data in forecasts.items():
                key = f"forecast:nwps:{loc.value}:{spot_id}"
                pipe.setex(key, timedelta(hours=14), json.dumps(spot_data))

            pipe.execute()

            file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
            file_path.unlink(missing_ok=True)

            logger.info(
                f"[NWPS] Successfully added forecast data for {loc.value} — {analysis_hour:02d}z",
                extra={
                    "location": loc.value,
                    "analysis_hour": analysis_hour,
                    "spots_processed": len(forecasts),
                },
            )

            return {
                "location": loc.value,
                "analysis_hour": analysis_hour,
                "spots_processed": len(forecasts),
                "file_size_mb": file_size_mb,
            }

        except HTTPStatusError as e:
            if e.response.status_code == 404:
                if self.request.retries < self.max_retries:
                    logger.warning(
                        f"[NWPS] GRIB2 file not ready for {loc.value}, retrying in {retry_countdown}s",
                        extra={
                            "location": loc.value,
                            "attempt": self.requests.retries + 1,
                            "max_retries": self.max_retries,
                        },
                    )
                    raise self.retry(exc=e, countdown=retry_countdown)
                else:
                    logger.error(f"[NWPS] HTTP {e.response.status_code} error")
                    raise
        except (NetworkError, TimeoutException) as e:
            if self.request.retries < self.max_retries:
                logger.warning(f"[NWPS] Network error, retrying in {retry_countdown}s")
                raise self.retry(exc=e, countdown=retry_countdown)
            else:
                raise
