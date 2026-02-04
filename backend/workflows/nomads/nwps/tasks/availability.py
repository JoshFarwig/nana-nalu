from datetime import date, datetime, time, timedelta, timezone
from prefect import task, get_run_logger

from services.forecast.nomads_config import NWPSConfig
from core.http import SyncHTTPManager

from workflows.resources import get_resources


@task(name="nwps-check-availability", retries=2, retry_delay_seconds=30)
def check_availability(
    config: NWPSConfig,
    max_lookback_hours: int,
    last_run_time: datetime | None = None,
) -> tuple[date, time] | None:
    """
    Find the most recent available model run by checking NOMADS server.

    Searches backward from now until either:
    - Finding an available run, OR
    - Reaching the last successfully fetched run time, OR
    - Reaching max_lookback_hours

    Args:
        config: NWPS configuration for the region
        last_run_time: Timestamp of last successful fetch (stops search here)
        max_lookback_hours: Fallback max search window if no last_run_time

    Returns:
        (forecast_date, analysis_time) tuple or None if no run available
    """
    logger = get_run_logger()
    resources = get_resources()

    now = datetime.now(timezone.utc)

    if last_run_time:
        cutoff = last_run_time
        logger.debug(
            f"Searching from now back to last run: {last_run_time}",
            extra={"last_run_time": last_run_time},
        )
    else:
        cutoff = now - timedelta(hours=max_lookback_hours)
        logger.debug(f"No last run time, searching back {max_lookback_hours}h")

    current = now.replace(minute=0, second=0, microsecond=0)

    while current >= cutoff:
        check_date = current.date()
        analysis_time = current.time()

        if _run_exists(config, resources.http, check_date, analysis_time):
            logger.info(
                f"Found available NOMADS run: {check_date} {analysis_time.strftime('%H:%M')} UTC",
                extra={"date": str(check_date), "hour": analysis_time.hour},
            )
            return (check_date, analysis_time)

        current -= timedelta(hours=1)

    if last_run_time:
        logger.warning(
            f"No new runs found since last run at {last_run_time.isoformat()}"
        )
    else:
        logger.warning(f"No runs found in last {max_lookback_hours} hours")

    return None


def _run_exists(
    config: NWPSConfig,
    http: SyncHTTPManager,
    forecast_date: date,
    analysis_time: time,
) -> bool:
    """
    Check if a specific run's GRIB file exists on NOMADS.

    Uses HEAD request to check existence without downloading.
    NOMADS returns 403 for non-existent directories/files.
    """
    url = _build_check_url(config, forecast_date, analysis_time)

    try:
        response = http._client.head(url, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def _build_check_url(
    config: NWPSConfig, forecast_date: date, analysis_time: time
) -> str:
    """Build URL to check if a specific run's GRIB file exists."""
    date_str = forecast_date.strftime("%Y%m%d")
    hour_str = analysis_time.strftime("%H")
    filename = config.construct_filename(analysis_time, forecast_date)

    return (
        f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod/"
        f"{config.nomads_region}.{date_str}/{config.wfo.value}/"
        f"{hour_str}/{config.cg}/{filename}"
    )
