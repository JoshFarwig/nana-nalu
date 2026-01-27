from prefect import task, get_run_logger

from services.forecast.nomads_config import NWPSConfig
from workflows.nomads.mapper import map_nwps_forecast
from services.forecast.forecast_schema import ProviderForecast


@task(name="nwps-transform-forecasts")
def transform_forecasts(
    raw_forecasts: dict[int, dict],
    config: NWPSConfig,
) -> dict[int, ProviderForecast]:
    """
    Transform raw NWPS forecast data to unified ProviderForecast schema.

    Maps provider-specific field names, units, and structures to the
    standardized schema used across all forecast providers.

    Args:
        raw_forecasts: Dictionary mapping spot_id -> raw forecast data
        config: NWPS configuration containing data summary info

    Returns:
        Dictionary mapping spot_id -> ProviderForecast
    """
    logger = get_run_logger()

    if not raw_forecasts:
        logger.warning("No raw forecasts to transform")
        return {}

    region = config.region.value
    provider_forecasts = {
        spot_id: map_nwps_forecast(spot_id, region, raw_data, config.data_summary)
        for spot_id, raw_data in raw_forecasts.items()
    }

    logger.info(
        f"Transformed {len(provider_forecasts)} forecasts to unified schema",
        extra={"spot_ids": list(provider_forecasts.keys())},
    )

    return provider_forecasts
