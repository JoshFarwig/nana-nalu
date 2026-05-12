import logging

logger = logging.getLogger(__name__)


def snap_lat_lon(
    lat_origin: float,
    lon_origin: float,
    lat_res: float,
    lon_res: float,
    user_lat: float,
    user_lon: float,
) -> tuple[float, float]:
    """
    Nearest neighbor snap, requires lon 0-360 to work as intended
    """
    snapped_lat = lat_origin + round((user_lat - lat_origin) / lat_res) * lat_res
    snapped_lon = lon_origin + round((user_lon - lon_origin) / lon_res) * lon_res
    return (snapped_lat, snapped_lon)
