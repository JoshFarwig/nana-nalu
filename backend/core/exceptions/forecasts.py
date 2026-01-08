from http import HTTPStatus
from core.exceptions.base import NanaNaluException


# =======================
# BASE FORECAST EXCEPTION
# =======================


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


# =======================
# FORECAST EXCEPTIONS
# =======================


class NoForecastDataError(ForecastError):
    """Raised when no forecast data available in Redis (could be expired, not yet fetched, or provider down)"""

    def __init__(
        self,
        spot_id: int,
        provider: str | None = None,
        model: str | None = None,
        reason: str | None = None,
    ):
        msg = f"No forecast data available for spot {spot_id}"
        if provider and model:
            msg += f" from {provider}:{model}"
        elif provider:
            msg += f" from provider {provider}"

        if reason:
            msg += f". {reason}"
        else:
            msg += ". Data may be expired (TTL), not yet available, or provider skipped this run."

        details = {"spot_id": spot_id, "provider": provider, "model": model}
        if reason:
            details["reason"] = reason

        super().__init__(
            message=msg,
            error_code="no_forecast_data",
            status_code=HTTPStatus.NOT_FOUND,
            details=details,
        )


class InvalidProviderError(ForecastError):
    """Raised when provider name is not recognized"""

    def __init__(self, provider: str, available_providers: list[str] | None = None):
        msg = f"Provider '{provider}' is not supported"
        details: dict[str, str | list[str]] = {"provider": provider}

        if available_providers:
            msg += f". Available providers: {', '.join(available_providers)}"
            details["available_providers"] = available_providers

        super().__init__(
            message=msg,
            error_code="invalid_provider",
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )


class InvalidModelError(ForecastError):
    """Raised when model name is not supported for given provider"""

    def __init__(
        self, provider: str, model: str, available_models: list[str] | None = None
    ):
        msg = f"Model '{model}' is not supported for provider '{provider}'"
        details: dict[str, str | list[str]] = {"provider": provider, "model": model}

        if available_models:
            msg += f". Available models: {', '.join(available_models)}"
            details["available_models"] = available_models

        super().__init__(
            message=msg,
            error_code="invalid_model",
            status_code=HTTPStatus.BAD_REQUEST,
            details=details,
        )
