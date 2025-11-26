import logging

from utils.location import Location
from services.forecast.providers.nwps.config import (
    get_nwps_configs,
    NWPSModelConfig,
)

logger = logging.getLogger(__name__)


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

    for location, _ in covering_locations:
        key = f"forecast:nwps:{location.value}:{spot_id}"
        keys[location.value] = key

    return keys
