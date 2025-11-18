from typing import Literal
import logging

logger = logging.getLogger(__name__)

EPSILON = 1e-9  # small fault tolerance for floating point errors
LAT_MIN = -90.0
LAT_MAX = 90.0
LON_SIGNED_MIN = -180.0
LON_SIGNED_MAX = 180.0
LON_UNSIGNED_MIN = 0.0
LON_UNSIGNED_MAX = 360.0


def valid_longitude(
    longitude: float, range_type: Literal["signed", "unsigned"]
) -> bool:
    if range_type == "signed":
        return (LON_SIGNED_MIN - EPSILON) <= longitude <= (LON_SIGNED_MAX + EPSILON)
    return (LON_UNSIGNED_MIN - EPSILON) <= longitude <= (LON_UNSIGNED_MAX + EPSILON)


def valid_latitude(latitude: float) -> bool:
    return (LAT_MIN - EPSILON) <= latitude <= (LAT_MAX + EPSILON)


def valid_longitude_range(
    long_min: float, long_max: float, range_type: Literal["signed", "unsigned"]
) -> bool:
    return (
        valid_longitude(long_min, range_type)
        and valid_longitude(long_max, range_type)
        and long_min <= long_max
    )


def valid_latitude_range(lat_min: float, lat_max: float) -> bool:
    return valid_latitude(lat_min) and valid_latitude(lat_max) and lat_min <= lat_max


def longitude_to_360(longitude: float, precision: int = 7) -> float:
    if not valid_longitude(longitude, range_type="signed"):
        raise ValueError(f"Longitude must be in range [-180, 180], got {longitude}")
    return round(longitude % 360, precision)


def longitude_to_180(longitude: float, precision: int = 7) -> float:
    if not valid_longitude(longitude, range_type="unsigned"):
        raise ValueError(f"Longitude must be in range [0, 360], got {longitude}")
    return round(((longitude + 180) % 360) - 180, precision)


# TODO: need to rewrite haversine distance calc, plus new kdtree and nearest neighbor methods
