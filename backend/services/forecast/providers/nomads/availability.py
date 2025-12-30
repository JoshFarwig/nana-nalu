from datetime import date, time, timedelta, timezone, datetime
from core.http import SyncHTTPManager
from .config import NWPSConfig
import logging

logger = logging.getLogger(__name__)


class NOMADSAvailabilityChecker:
    """Check NOMADS server for latest available model run."""

    def __init__(self, config: NWPSConfig, http_manager: SyncHTTPManager):
        self.config = config
        self.http = http_manager

    def get_latest_available_run(
        self,
        last_run_time: datetime | None = None,
        max_lookback_hours: int = 24,
    ) -> tuple[date, time] | None:
        """
        Find the most recent available model run by checking NOMADS server.

        Searches backward from now until either:
        - Finding an available run, OR
        - Reaching the last successfully fetched run time, OR
        - Reaching max_lookback_hours (24h default)

        Args:
            last_run_time: Timestamp of last successful fetch (stops search here)
            max_lookback_hours: Fallback max search window if no last_run_time

        Returns (forecast_date, analysis_time) or None.
        """
        now = datetime.now(timezone.utc)

        # use last run time as cutoff if provided, otherwise use max lookback
        if last_run_time:
            cutoff = last_run_time
            logger.debug(f"Searching from now back to last run: {last_run_time}")
        else:
            cutoff = now - timedelta(hours=max_lookback_hours)
            logger.debug(f"No last run time, searching back {max_lookback_hours}h")

        # walk backward hour by hour from now
        current = now.replace(minute=0, second=0, microsecond=0)

        while current >= cutoff:
            check_date = current.date()
            analysis_time = current.time()

            if self._run_exists(check_date, analysis_time):
                logger.info(
                    f"Found available NOMADS run: {check_date} {analysis_time.strftime('%H:%M %Z')}",
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

    def _run_exists(self, forecast_date: date, analysis_time: time) -> bool:
        """
        Check if a specific run's GRIB file exists on NOMADS.

        Note: NOMADS will return a 403 for non-existent directories/files,
        so we only consider 200 as success.
        """
        url = self._build_check_url(forecast_date, analysis_time)

        try:
            # HEAD request to check existence without downloading
            response = self.http._client.head(url, timeout=5)
            return response.status_code == 200
        except Exception:
            # network errors, timeouts, bad requests. - treat as non-existent
            return False

    def _build_check_url(self, forecast_date: date, analysis_time: time) -> str:
        """Build URL to check if a specific run's GRIB file exists."""
        date_str = forecast_date.strftime("%Y%m%d")
        hour_str = analysis_time.strftime("%H")

        # get the actual filename for this run
        filename = self.config.construct_filename(analysis_time, forecast_date)

        # direct NOMADS path to the actual GRIB2 file
        return (
            f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod/"
            f"{self.config.region}.{date_str}/{self.config.wfo.value}/"
            f"{hour_str}/{self.config.grid.cg}/{filename}"
        )
