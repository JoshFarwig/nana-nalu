from typing import Literal

EPSILON = 1e-9  # small fault tolerance for floating point errors
EARTH_MEAN_RADIUS_KM = 6371
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


def longitude_to_360(longitude: float, precision: int) -> float:
    if not valid_longitude(longitude, range_type="signed"):
        raise ValueError(f"Longitude must be in range [-180, 180], got {longitude}")
    return round(longitude % 360, precision)


def longitude_to_180(longitude: float, precision: int) -> float:
    if not valid_longitude(longitude, range_type="unsigned"):
        raise ValueError(f"Longitude must be in range [0, 360], got {longitude}")
    return round(((longitude + 180) % 360) - 180, precision)


def wave_direction_to_toward(direction_from: float | None) -> float | None:
    """
    Convert wave direction from 'from' convention to 'toward' convention.

    Meteorological convention uses "from" (where waves originate).
    Oceanographic convention uses "toward" (where waves travel).

    Args:
        direction_from: Wave direction in degrees true (from), or None

    Returns:
        Wave direction in degrees true (toward), or None if input is None

    Example:
        >>> wave_direction_to_toward(90)  # Waves from east
        270  # Waves traveling west
    """
    if direction_from is None:
        return None
    return (direction_from + 180) % 360
