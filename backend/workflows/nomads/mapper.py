from services.forecast.forecast_schema import (
    GridMetadata,
    TideData,
    WaveData,
    WindData,
    ForecastPoint,
    ForecastProvider,
    ForecastModel,
    ProviderForecast,
)


def map_nwps_forecast(
    spot_id: int, location: str, nwps_forecast_data: dict, data_summary: dict[str, str]
) -> ProviderForecast:
    """
    Map NWPS data fields to unified schema.

    Args:
        spot_id: The surf spot ID
        location: Regional variant (e.g., "maui", "oahu")
        nwps_forecast_data: Raw data from NWPS GRIB2 extraction
        data_summary: Category-level descriptions from config
    """

    forecast = []

    for i, valid_time in enumerate(nwps_forecast_data["valid_times"]):
        wave = WaveData(
            height=nwps_forecast_data["data"]["swh"][i],
            swell_height=nwps_forecast_data["data"]["shts"][i],
            peak_direction=nwps_forecast_data["data"]["dirpw"][i],
            peak_period=nwps_forecast_data["data"]["perpw"][i],
        )

        wind = WindData(
            speed=nwps_forecast_data["data"]["ws"][i],
            direction=nwps_forecast_data["data"]["wdir"][i],
        )

        tide = TideData(height=nwps_forecast_data["data"]["zos"][i])

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
