from datetime import datetime, timezone

import pytest

from services.forecast.forecast_schema import (
    ForecastModel,
    ForecastProvider,
    ForecastPoint,
    ProviderForecastResponse,
    SwellPartition,
    TideData,
    WaveData,
    WindData,
)
from utils.region import Region


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def valid_time():
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def wave_data_with_swells():
    return WaveData(
        significant_height=2.1,
        peak_period=14.0,
        peak_direction=315.0,
        primary_swell=SwellPartition(height=1.8, period=14.0, direction=315.0),
        secondary_swell=SwellPartition(height=0.8, period=9.0, direction=270.0),
    )


@pytest.fixture
def wind_data():
    return WindData(speed=5.5, direction=45.0)


@pytest.fixture
def tide_data():
    return TideData(height=0.3)


@pytest.fixture
def full_forecast_point(valid_time, wave_data_with_swells, wind_data, tide_data):
    return ForecastPoint(
        valid_time=valid_time,
        wave=wave_data_with_swells,
        wind=wind_data,
        tide=tide_data,
    )


@pytest.fixture
def provider_forecast_response(full_forecast_point):
    return ProviderForecastResponse(
        provider=ForecastProvider.NOMADS,
        model=ForecastModel.NWPS,
        region=Region.MAUI,
        forecast=[full_forecast_point],
    )


# ============================================================================
# Tests: _compute_units
# ============================================================================


@pytest.mark.unit
class TestComputeUnits:
    def test_wave_only(self, valid_time):
        point = ForecastPoint(
            valid_time=valid_time,
            wave=WaveData(significant_height=2.0, peak_period=12.0),
        )
        response = ProviderForecastResponse(
            provider=ForecastProvider.NOMADS,
            model=ForecastModel.NWPS,
            region=Region.MAUI,
            forecast=[point],
        )
        units = response._compute_units()

        assert "wave" in units
        assert "wind" not in units
        assert "tide" not in units
        assert "current" not in units

    def test_wave_and_wind_both_present(self, provider_forecast_response):
        units = provider_forecast_response._compute_units()

        assert "wave" in units
        assert "wind" in units

    def test_excludes_null_fields_from_units(self, valid_time):
        point = ForecastPoint(
            valid_time=valid_time,
            wave=WaveData(significant_height=2.0),
        )
        response = ProviderForecastResponse(
            provider=ForecastProvider.NOMADS,
            model=ForecastModel.NWPS,
            region=Region.MAUI,
            forecast=[point],
        )
        units = response._compute_units()

        assert "significant_height" in units["wave"]
        assert "peak_period" not in units["wave"]
        assert "peak_direction" not in units["wave"]

    def test_swell_partitions_flattened(self, valid_time):
        point = ForecastPoint(
            valid_time=valid_time,
            wave=WaveData(
                significant_height=2.1,
                primary_swell=SwellPartition(height=1.8, period=14.0),
                secondary_swell=SwellPartition(height=0.8),
            ),
        )
        response = ProviderForecastResponse(
            provider=ForecastProvider.NOMADS,
            model=ForecastModel.NWPS,
            region=Region.MAUI,
            forecast=[point],
        )
        wave_units = response._compute_units()["wave"]

        assert "swell_height" in wave_units
        assert "swell_period" in wave_units
        assert "swell_direction" not in wave_units  # no swell had direction set
        assert "primary_swell" not in wave_units    # nested keys must not appear
        assert "secondary_swell" not in wave_units
