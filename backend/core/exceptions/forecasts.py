from http import HTTPStatus
from enum import Enum

from core.exceptions.base import NanaNaluException


class ForecastError(NanaNaluException):
    """Base exception for forecast errors"""

    client_safe_details: bool = True

    def __init__(
        self,
        message: str,
        error_code: str | None = "forecast_error",
        status_code: int | None = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


class InvalidFilterReason(str, Enum):
    OUT_OF_BOUNDS = "out_of_bounds"  # coords outside any ingested grid
    TIME_RANGE = "time_range"  # start > end, future date, etc
    TIME_HORIZON = "time_horizon"  # outside model run's forecast horizon


class InvalidForecastFilterError(ForecastError):
    """Input parameters rejected — not a data miss, a malformed query."""

    _MESSAGES = {
        InvalidFilterReason.OUT_OF_BOUNDS: "Coordinates are outside the available grid.",
        InvalidFilterReason.TIME_RANGE: "Requested time range is invalid.",
        InvalidFilterReason.TIME_HORIZON: "Requested time is outside the forecast horizon.",
    }

    def __init__(self, reason: InvalidFilterReason, context: dict | None = None):
        details = {"reason": reason.value}
        if context:
            details.update(context)
        super().__init__(
            message=self._MESSAGES[reason],
            error_code="invalid_forecast_filter",
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )


class NoDataReason(str, Enum):
    TIME_FILTER = "time_filter"  # time valid but no row at exact moment
    COORDINATES = "coordinates"  # coords valid but snapped cell unfilled
    BOTH = "both"
    UNKNOWN = "unknown"


class NoForecastDataError(ForecastError):
    """Model run exists but no forecast rows match the query (coords or time filter)."""

    _MESSAGES = {
        NoDataReason.TIME_FILTER: "No forecast data for the requested time.",
        NoDataReason.COORDINATES: "No forecast data at the requested coordinates.",
        NoDataReason.BOTH: "No forecast data for the requested coordinates and time.",
        NoDataReason.UNKNOWN: "No forecast data matches this query.",
    }

    def __init__(
        self,
        provider: str,
        model: str,
        region: str,
        reason: NoDataReason = NoDataReason.UNKNOWN,
        context: dict | None = None,
    ):
        details: dict = {
            "provider": provider,
            "model": model,
            "region": region,
            "reason": reason.value,
        }
        if context:
            details.update(context)

        super().__init__(
            message=self._MESSAGES[reason],
            error_code="no_forecast_data",
            status_code=HTTPStatus.NOT_FOUND,
            details=details,
        )


class InvalidProviderError(ForecastError):
    """Provider name is not recognized."""

    def __init__(self, provider: str, available_providers: list[str] | None = None):
        details: dict[str, str | list[str]] = {"provider": provider}
        if available_providers:
            details["available_providers"] = available_providers

        super().__init__(
            message="Selected provider is not available.",
            error_code="invalid_provider",
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )


class NoModelRunError(ForecastError):
    """No model runs ingested for provider/model/region combo."""

    def __init__(self, provider: str, model: str, region: str):
        super().__init__(
            message="No forecast run is available for this selection.",
            error_code="no_model_run",
            status_code=HTTPStatus.NOT_FOUND,
            details={"provider": provider, "model": model, "region": region},
        )


class InvalidModelError(ForecastError):
    """Model name is not supported for the given provider."""

    def __init__(
        self, provider: str, model: str, available_models: list[str] | None = None
    ):
        details: dict[str, str | list[str]] = {"provider": provider, "model": model}
        if available_models:
            details["available_models"] = available_models

        super().__init__(
            message="Selected model is not available for this provider.",
            error_code="invalid_model",
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )


class UnknownRegionError(ForecastError):
    """Region is a valid enum value but not enabled in this deployment."""

    def __init__(self, region: str, available_regions: list[str]):
        super().__init__(
            message="Selected region is not enabled.",
            error_code="unknown_region",
            status_code=HTTPStatus.BAD_REQUEST,
            details={"region": region, "available_regions": available_regions},
        )


class UnknownRunComboError(ForecastError):
    """Provider/model/region triple is well-typed but has no registered config."""

    def __init__(self, provider: str, model: str, region: str, available: list[dict]):
        super().__init__(
            message="That provider, model, and region combination isn't available.",
            error_code="unknown_run_combo",
            status_code=HTTPStatus.BAD_REQUEST,
            details={
                "provider": provider,
                "model": model,
                "region": region,
                "available": available,
            },
        )
