from http import HTTPStatus
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


class NoModelRunError(ForecastError):
    """No model runs ingested for provider/model/region combo."""

    def __init__(self, provider: str, model: str, region: str):
        super().__init__(
            message=f"No model run found for {provider}:{model}:{region}",
            error_code="no_model_run",
            status_code=HTTPStatus.NOT_FOUND,
            details={"provider": provider, "model": model, "region": region},
        )


class NoForecastDataError(ForecastError):
    """Model run exists but no forecast rows match the query (coords or time filter)."""

    def __init__(
        self,
        provider: str,
        model: str,
        region: str,
        reason: str | None = None,
    ):
        msg = f"No forecast data for {provider}:{model}:{region}"
        if reason:
            msg += f". {reason}"

        super().__init__(
            message=msg,
            error_code="no_forecast_data",
            status_code=HTTPStatus.NOT_FOUND,
            details={"provider": provider, "model": model, "region": region},
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
