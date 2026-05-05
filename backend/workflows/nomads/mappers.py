from services.forecast.forecast_schema import (
    GridCellForecast,
    SwellPartition,
    TideData,
    WaveData,
    WindData,
    ForecastPoint,
)


def map_nwps_forecast(
    lat: float, lon: float, raw_data: dict, data_summary: dict[str, str]
) -> GridCellForecast:
    """
    Map NWPS GRIB2 data fields to unified GridCellForecast schema.

    NWPS provides only swell height (shts) — no separate swell direction or period.
    All directions stored as "from" (degrees true). No unit conversion needed.
    """
    valid_times = raw_data["valid_times"]
    data = raw_data["data"]
    forecast = []

    for i, valid_time in enumerate(valid_times):
        wave = WaveData(
            significant_height=float(data["swh"][i]),
            peak_period=float(data["perpw"][i]),
            peak_direction=float(data["dirpw"][i]),
            primary_swell=SwellPartition(height=float(data["shts"][i])),
        )
        wind = WindData(
            speed=float(data["ws"][i]),
            direction=float(data["wdir"][i]),
        )
        tide = TideData(height=float(data["zos"][i]))

        forecast.append(
            ForecastPoint(valid_time=valid_time, wave=wave, wind=wind, tide=tide)
        )

    return GridCellForecast(lat=lat, lon=lon, forecast=forecast)
