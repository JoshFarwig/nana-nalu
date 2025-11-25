import logging
from datetime import datetime, timedelta, timezone

from utils.location import Location
from services.forecast.providers.nwps.config import (
    get_nwps_configs,
    NWPSModelConfig,
)

logger = logging.getLogger(__name__)


def get_latest_available_analysis_hour(
    config: NWPSModelConfig,
    now: datetime | None = None,
) -> int | None:
    """Find the most recent analysis hour whose forecast should be available."""
    if now is None:
        now = datetime.now(timezone.utc)

    forecast_ttl = timedelta(hours=14)
    available = []

    for _, analysis_time in config.model_analysis_times.items():
        ready_today = (
            datetime.combine(now.date(), analysis_time, tzinfo=timezone.utc)
            + config.model_long_wait_time
        )

        ready_yesterday = ready_today - timedelta(days=1)

        for ready_dt in [ready_today, ready_yesterday]:
            expires_at = ready_dt + forecast_ttl
            if ready_dt <= now < expires_at:
                available.append((analysis_time.hour, ready_dt))

    if not available:
        return None

    return max(available, key=lambda x: x[1])[0]


def get_covering_locations(
    lat: float,
    lon: float,
) -> list[tuple[Location, NWPSModelConfig]]:
    """Find all NWPS location grids that cover a given coordinate."""
    configs = get_nwps_configs()
    covering = []

    for location, config in configs.items():
        grid = config.grid
        if (
            grid.lat_min <= lat <= grid.lat_max
            and grid.long_min <= lon <= grid.long_max
        ):
            covering.append((location, config))

    return covering


def build_forecast_keys_for_spot(
    spot_id: int,
    lat: float,
    lon: float,
) -> dict[str, str]:
    """
    Build Redis keys for all available NWPS forecasts for a spot.

    Simplified to not require analysis time prediction - keys now store
    latest forecast only, with actual analysis hour embedded in data.
    """
    covering_locations = get_covering_locations(lat, lon)
    keys = {}

    for location, config in covering_locations:
        # Simplified key: no analysis hour (always fetches latest)
        key = f"forecast:nwps:{location.value}:{spot_id}"
        keys[location.value] = key

    return keys
