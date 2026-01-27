"""
Transform raw PacIOOS tide data to unified ProviderForecast schema.
"""

from prefect import task, get_run_logger

from services.forecast.pacioos_config import PacIOOSModelConfig
from workflows.pacioos.mapper import map_pacioos_tide_forecast
from services.forecast.forecast_schema import ProviderForecast


@task(name="tide-mhi-transform-forecasts")
def transform_forecasts(
    raw_forecasts: dict[int, dict],
    config: PacIOOSModelConfig,
) -> dict[int, ProviderForecast]:
    """
    Transform raw PacIOOS tide data to unified ProviderForecast schema.

    Maps provider-specific field names, units, and structures to the
    standardized schema used across all forecast providers.

    Args:
        raw_forecasts: Dictionary mapping spot_id -> raw forecast data
        config: PacIOOS model configuration containing data summary info

    Returns:
        Dictionary mapping spot_id -> ProviderForecast
    """
    logger = get_run_logger()

    if not raw_forecasts:
        logger.warning("No raw forecasts to transform")
        return {}

    region = config.region.value
    provider_forecasts = {
        spot_id: map_pacioos_tide_forecast(spot_id, region, raw_data, config.data_summary)
        for spot_id, raw_data in raw_forecasts.items()
    }

    logger.info(
        f"Transformed {len(provider_forecasts)} forecasts to unified schema",
        extra={"spot_ids": list(provider_forecasts.keys())},
    )

    return provider_forecasts
