from schemas.forecast_schema import (
    TideData,
    ForecastPoint,
)
# TODO: GridCellForecast removed from forecast_schema — update return type

from domain.region import Region


def map_pacioos_tide_forecast(
    lat: float, lon: float, raw_data: dict, data_summary: dict[str, str]
) -> GridCellForecast:
    """
    Map PacIOOS Tide model ssh field to unified GridCellForecast schema.

    ssh (sea surface height) → tide.height. No currents — use ROMS for those.
    """
    forecast = [
        ForecastPoint(
            valid_time=valid_time,
            tide=TideData(height=round(float(raw_data["data"]["ssh"][i]), 2)),
        )
        for i, valid_time in enumerate(raw_data["valid_times"])
    ]

    return forecast


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
