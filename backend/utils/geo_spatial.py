import logging
from decimal import Decimal

from schemas.forecast_schema import MAX_COORD_DP, CoordBounds

logger = logging.getLogger(__name__)


def coord_precision(res: float) -> int:
    """
    Decimals needed to represent a grid cell at the given resolution without
    false precision. Cell bounds land on center ± res/2, so the meaningful
    decimal count tracks `res`. Clamped to [0, MAX_COORD_DP].
    """
    if res <= 0:
        return 0
    # Quantize to the floor first: float32/arithmetic noise (e.g. 0.1 stored as
    # 0.10000000149) gives a long repr whose place-count would always slam into
    # MAX_COORD_DP, silently restoring false precision. Rounding to the floor
    # recovers the author-intended res (0.1 -> "0.1") before counting.
    quantized = round(res, MAX_COORD_DP)
    # Decimals in `res` itself, then +1 for the half-step (res/2) that bounds
    # land on (e.g. 0.25 -> bounds offset 0.125, one extra decimal). Decimal on
    # str() counts places exactly, unlike log10 which only tracks magnitude.
    res_dp = max(0, -Decimal(str(quantized)).normalize().as_tuple().exponent)
    return min(MAX_COORD_DP, res_dp + 1)


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
    lat_dp = coord_precision(lat_res)
    lon_dp = coord_precision(lon_res)

    lat_max = round(snapped_lat + (lat_res / 2.0), lat_dp)
    lat_min = round(snapped_lat - (lat_res / 2.0), lat_dp)
    lon_max = round(snapped_lon + (lon_res / 2.0), lon_dp)
    lon_min = round(snapped_lon - (lon_res / 2.0), lon_dp)

    return CoordBounds(
        lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max
    )
