import logging

from schemas.forecast_schema import CoordBounds

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


def calc_cell_bounds(
    snapped_lat: float,
    snapped_lon: float,
    lat_res: float,
    lon_res: float,
) -> CoordBounds:
    """
    Calculate the cell bounds of the user selected snap. Used inconjunction w/ snap_lat_lon

    The snapped point is the grid node = cell center, so the cell extends half a
    resolution step in each direction. Returns lon in 0-360 (frontend normalizes).
    """
    lat_max = snapped_lat + (lat_res / 2.0)
    lat_min = snapped_lat - (lat_res / 2.0)
    lon_max = snapped_lon + (lon_res / 2.0)
    lon_min = snapped_lon - (lon_res / 2.0)

    return CoordBounds(
        lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max
    )
