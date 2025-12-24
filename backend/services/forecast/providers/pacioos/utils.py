import math
from typing import Any


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def compute_current_polar(
    u: float | None, v: float | None
) -> tuple[float | None, float | None] | None:
    if u is None or v is None:
        return None

    speed = math.sqrt(u**2 + v**2)
    # NOTE: current is flowing TOWARD direction
    direction = math.degrees(math.atan2(u, v) + 360) % 360

    return round(speed, 3), round(direction, 1)
