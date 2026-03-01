import logging

from services.forecast.forecast_schema import (
    GridMetadata,
    TideData,
    ForecastPoint,
    ForecastProvider,
    ForecastModel,
    ProviderForecast,
)
from utils.region import Region

logger = logging.getLogger(__name__)


def map_pacioos_tide_forecast(
    spot_id: int, region: Region, raw_data: dict, data_summary: dict[str, str]
) -> ProviderForecast:
    """
    Map PacIOOS Tide model forecast to unified schema.

    Tide model provides:
    - ssh: Sea surface height (meters)

    Note: Tidal currents (u/v) are not included. For comprehensive currents,
    use ROMS model which includes tidal + wind + wave-driven components.

    Maps to: tide.height
    """
    forecast = []

    for i, valid_time in enumerate(raw_data["valid_times"]):
        # Sea level from sea surface height
        tide = TideData(height=round(raw_data["data"]["ssh"][i], 2))

        forecast.append(ForecastPoint(valid_time=valid_time, tide=tide))

    return ProviderForecast(
        spot_id=spot_id,
        provider=ForecastProvider.PACIOOS,
        model=ForecastModel.TIDE,
        region=region,
        grid_metadata=GridMetadata(
            selected_lat=raw_data["grid_metadata"]["selected_lat"],
            selected_lon=raw_data["grid_metadata"]["selected_lon"],
            distance_km=raw_data["grid_metadata"]["distance_km"],
        ),
        data_summary=data_summary,
        forecast=forecast,
    )


def map_pacioos_swan_forecast(
    spot_id: int, region: Region, raw_data: dict, data_summary: dict[str, str]
):
    """
    Map PacIOOS SWAN wave model forecast to unified schema.

    Maps to: wave.significant_height, wave.peak_direction, wave.peak_period
    """
    # TODO:
    pass


def map_pacioos_wrf_forecast(
    spot_id: int, region: Region, raw_data: dict, data_summary: dict[str, str]
):
    """
    Map PacIOOS WRF atmospheric model forecast to unified schema.

    Maps to: wind.speed, wind.direction (degrees FROM)
    """
    # TODO:
    pass
