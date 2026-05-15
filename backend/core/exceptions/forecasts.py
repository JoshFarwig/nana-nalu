from http import HTTPStatus
from enum import Enum

from core.exceptions.base import NanaNaluException


class ForecastError(NanaNaluException):
    """Base exception for forecast errors"""

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
        InvalidFilterReason.OUT_OF_BOUNDS: "Coordinates outside grid extent",
        InvalidFilterReason.TIME_RANGE: "Invalid time range",
        InvalidFilterReason.TIME_HORIZON: "Time outside forecast horizon",
    }

    def __init__(self, reason: InvalidFilterReason, context: dict | None = None):
        details = {"reason": reason.value}
        if context:
            details.update(context)
        super().__init__(
            message=f"Invalid forecast filter: {self._MESSAGES[reason]}",
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
        NoDataReason.TIME_FILTER: "No data for requested time range",
        NoDataReason.COORDINATES: "No data at requested coordinates",
        NoDataReason.BOTH: "No data for requested coordinates and time",
        NoDataReason.UNKNOWN: "Query matched no rows",
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
            message=f"No forecast data for {provider}:{model}:{region}. {self._MESSAGES[reason]}",
            error_code="no_forecast_data",
            status_code=HTTPStatus.NOT_FOUND,
            details=details,
        )


class InvalidProviderError(ForecastError):
    """Provider name is not recognized."""

    def __init__(self, provider: str, available_providers: list[str] | None = None):
        msg = f"Provider '{provider}' is not supported"
        details: dict[str, str | list[str]] = {"provider": provider}

        if available_providers:
            msg += f". Available: {', '.join(available_providers)}"
            details["available_providers"] = available_providers

        super().__init__(
            message=msg,
            error_code="invalid_provider",
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )


class NoModelRunError(ForecastError):
    """No model runs ingested for provider/model/region combo."""

    def __init__(self, provider: str, model: str, region: str):
        super().__init__(
            message=f"No model run found for {provider}:{model}:{region}",
            error_code="no_model_run",
            status_code=HTTPStatus.NOT_FOUND,
            details={"provider": provider, "model": model, "region": region},
        )


class InvalidModelError(ForecastError):
    """Model name is not supported for the given provider."""

    def __init__(
        self, provider: str, model: str, available_models: list[str] | None = None
    ):
        msg = f"Model '{model}' is not supported for provider '{provider}'"
        details: dict[str, str | list[str]] = {"provider": provider, "model": model}

        if available_models:
            msg += f". Available: {', '.join(available_models)}"
            details["available_models"] = available_models

        super().__init__(
            message=msg,
            error_code="invalid_model",
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )


class UnknownRegionError(ForecastError):
    """Region is a valid enum value but not enabled in this deployment."""

    def __init__(self, region: str, available_regions: list[str]):
        super().__init__(
            message=f"Region '{region}' is not enabled",
            error_code="unknown_region",
            status_code=HTTPStatus.BAD_REQUEST,
            details={"region": region, "available_regions": available_regions},
        )


class UnknownRunComboError(ForecastError):
    """Provider/model/region triple is well-typed but has no registered config."""

    def __init__(self, provider: str, model: str, region: str, available: list[dict]):
        super().__init__(
            message=f"No registered configuration for {provider}/{model}/{region}",
            error_code="unknown_run_combo",
            status_code=HTTPStatus.BAD_REQUEST,
            details={
                "provider": provider,
                "model": model,
                "region": region,
                "available": available,
            },
        )
