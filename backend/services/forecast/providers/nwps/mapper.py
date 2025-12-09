import logging
from datetime import datetime

from schemas.forecast_schema import (
    WaveData,
    WindData,
    TideData,
    CurrentData,
    ForecastPoint,
    ForecastProvider,
    ProviderForecast,
)

logger = logging.getLogger(__name__)


def map_nwps_forecast(spot_id: int, nwps_forecast_data: dict) -> ProviderForecast:
    """Map NWPS data fields to unified schema"""

    for i, valid_time in enumerate(nwps_forecast_data["valid_times"]):
wave = WaveData(
    height=nwps_forecast_data["data"]["swh"][i], 
    direction=nwps_forecast_data["data"]["dirpw"][i], 
    period=nwps_forecast_data["data"][][i], 
    height_swell= 

                )
