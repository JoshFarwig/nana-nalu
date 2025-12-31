"""Surf spot domain exceptions.

All exceptions related to surf spot operations, regardless of which layer raises them.
Can be used by repositories, services, or routes.
"""

from http import HTTPStatus
from core.exceptions.base import NanaNaluException
from utils.region import get_enabled_regions


# =======================
# BASE SURF SPOT EXCEPTION
# =======================


class SurfSpotError(NanaNaluException):
    """Base exception for surf spot errors"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "surf_spot_error",
        status_code: int | None = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


# =======================
# SURF SPOT EXCEPTIONS
# =======================


class SurfSpotNotFoundError(SurfSpotError):
    """Raised when surf spot doesn't exist in database"""

    def __init__(self, spot_id: int):
        super().__init__(
            message=f"Surf spot {spot_id} not found",
            error_code="surf_spot_not_found",
            status_code=HTTPStatus.NOT_FOUND,
            details={"spot_id": spot_id},
        )


class SurfSpotNotInRegionError(SurfSpotError):
    """Raised when a surf spot is created outside of supported regions"""

    def __init__(self, name: str, lat: float, lon: float):
        super().__init__(
            message=f"Spot: {name} at ({lat}, {lon}) is not in a supported forecast region",
            error_code="surf_spot_not_in_region",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            details={
                "name": name,
                "latitude": lat,
                "longitude": lon,
                "supported_regions": [region.value for region in get_enabled_regions()],
            },
        )


class InvalidCoordBoundsError(SurfSpotError):
    """Raised when coordinate bounds are invalid"""

    def __init__(
        self, lat_min: float, lat_max: float, long_min: float, long_max: float
    ):
        super().__init__(
            message=f"Invalid coordinate bounds: lat({lat_min}, {lat_max}), lon({long_min}, {long_max})",
            error_code="invalid_coord_bounds",
            status_code=HTTPStatus.BAD_REQUEST,
            details={
                "lat_min": lat_min,
                "lat_max": lat_max,
                "long_min": long_min,
                "long_max": long_max,
            },
        )
