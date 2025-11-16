EPSILON = 1e-9  # small fault tolerence for floating point errors


def longitude_to_360(longitude: float, precision: int = 7) -> float:
    if not (-180 - EPSILON) <= longitude <= (180 + EPSILON):
        raise ValueError("Longitude must be in range [-180, 180], got {longitude}")
    result = longitude % 360
    return round(result, precision)


def longitude_to_180(longitude: float, precision: int = 7) -> float:
    if not (0 - EPSILON) <= longitude <= (360 + EPSILON):
        raise ValueError("Longitude must be in range [0, 360], got {longitude}")
    result = ((longitude + 180) % 360) - 180
    return round(result, precision)
