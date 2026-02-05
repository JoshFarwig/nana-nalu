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
from utils.geo_validation import wave_direction_to_toward


def map_nwps_forecast(
    spot_id: int, location: str, nwps_forecast_data: dict, data_summary: dict[str, str]
) -> ProviderForecast:
    """
    Map NWPS data fields to unified schema.

    NWPS provides only swell height (shts) — no separate swell direction or period.
    Maps shts to primary_swell.height; period and direction remain None.

    Direction convention: NWPS reports wave direction as "from" (Degree true).
    Converted to "toward" at ingestion: (direction + 180) % 360.
    Wind direction remains "from" (meteorological convention).

    Args:
        spot_id: The surf spot ID
        location: Regional variant (e.g., "maui", "oahu")
        nwps_forecast_data: Raw data from NWPS GRIB2 extraction
        data_summary: Category-level descriptions from config
    """

    forecast = []

    for i, valid_time in enumerate(nwps_forecast_data["valid_times"]):
        data = nwps_forecast_data["data"]

        wave = WaveData(
            significant_height=data["swh"][i],
            peak_period=data["perpw"][i],
            peak_direction=wave_direction_to_toward(data["dirpw"][i]),
            primary_swell=SwellPartition(
                height=data["shts"][i],
            ),
        )

        wind = WindData(
            speed=data["ws"][i],
            direction=data["wdir"][i],
        )

        tide = TideData(height=data["zos"][i])

        forecast.append(
            ForecastPoint(valid_time=valid_time, wave=wave, wind=wind, tide=tide)
        )

    return ProviderForecast(
        spot_id=spot_id,
        provider=ForecastProvider.NOMADS,
        model=ForecastModel.NWPS,
        location=location,
        analysis_time=nwps_forecast_data["analysis_time"],
        grid_metadata=GridMetadata(
            selected_lat=nwps_forecast_data["grid_metadata"]["selected_lat"],
            selected_lon=nwps_forecast_data["grid_metadata"]["selected_lon"],
            distance_km=nwps_forecast_data["grid_metadata"]["distance_km"],
        ),
        data_summary=data_summary,
        forecast=forecast,
    )
