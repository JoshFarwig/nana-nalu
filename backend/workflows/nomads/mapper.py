from services.forecast.forecast_schema import (
    GridMetadata,
    SwellPartition,
    TideData,
    WaveData,
    WindData,
    ForecastPoint,
    ForecastProvider,
    ForecastModel,
    ProviderForecast,
)
from utils.region import Region


def map_nwps_forecast(
    spot_id: int, region: Region, nwps_forecast_data: dict, data_summary: dict[str, str]
) -> ProviderForecast:
    """
    Map NWPS data fields to unified schema.

    NWPS provides only swell height (shts) — no separate swell direction or period.
    Maps shts to primary_swell.height; period and direction remain None.

    Direction convention: all directions stored as "from" (degrees true).
    NWPS reports wave direction as "from" — no conversion needed.
    Wind direction is also "from" (meteorological convention).

    Args:
        spot_id: The surf spot ID
        region: Regional variant (e.g., "maui", "oahu")
        nwps_forecast_data: Raw data from NWPS GRIB2 extraction
        data_summary: Category-level descriptions from config
    """

    forecast = []

    for i, valid_time in enumerate(nwps_forecast_data["valid_times"]):
        data = nwps_forecast_data["data"]

        wave = WaveData(
            significant_height=round(data["swh"][i], 2),
            peak_period=round(data["perpw"][i], 1),
            peak_direction=round(data["dirpw"][i], 1),
            primary_swell=SwellPartition(
                height=round(data["shts"][i], 2),
            ),
        )

        wind = WindData(
            speed=round(data["ws"][i], 2),
            direction=round(data["wdir"][i], 1),
        )

        tide = TideData(height=round(data["zos"][i], 2))

        forecast.append(
            ForecastPoint(valid_time=valid_time, wave=wave, wind=wind, tide=tide)
        )

    return ProviderForecast(
        spot_id=spot_id,
        provider=ForecastProvider.NOMADS,
        model=ForecastModel.NWPS,
        region=region,
        analysis_time=nwps_forecast_data["analysis_time"],
        grid_metadata=GridMetadata(
            selected_lat=nwps_forecast_data["grid_metadata"]["selected_lat"],
            selected_lon=nwps_forecast_data["grid_metadata"]["selected_lon"],
            distance_km=nwps_forecast_data["grid_metadata"]["distance_km"],
        ),
        data_summary=data_summary,
        forecast=forecast,
    )
