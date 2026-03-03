from datetime import datetime, timezone

import pytest

from services.forecast.forecast_schema import ForecastModel, ForecastProvider
from utils.region import Region
from workflows.nomads.mapper import map_nwps_forecast


@pytest.fixture
def raw_nwps_data():
    return {
        "valid_times": [
            datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc),
        ],
        "analysis_time": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        "data": {
            "swh": [2.157, 1.843],
            "perpw": [14.32, 13.87],
            "dirpw": [315.42, 318.1],
            "shts": [1.823, 1.412],
            "ws": [5.521, 4.233],
            "wdir": [45.21, 48.9],
            "zos": [0.284, -0.143],
        },
        "grid_metadata": {
            "selected_lat": 20.8,
            "selected_lon": -156.3,
            "distance_km": 2.1,
        },
    }


@pytest.fixture
def result(raw_nwps_data):
    return map_nwps_forecast(
        spot_id=1,
        region=Region.MAUI,
        nwps_forecast_data=raw_nwps_data,
        data_summary={"wave": "Nearshore Wave Prediction System"},
    )


@pytest.mark.unit
class TestNWPSFieldMapping:
    def test_wave_fields_mapped_correctly(self, result):
        point = result.forecast[0]
        assert point.wave is not None
        assert point.wave.significant_height == pytest.approx(2.16)
        assert point.wave.peak_period == pytest.approx(14.3)
        assert point.wave.peak_direction == pytest.approx(315.4)

    def test_primary_swell_height_from_shts(self, result):
        # NWPS only provides swell height (shts), period and direction are None
        swell = result.forecast[0].wave.primary_swell
        assert swell is not None
        assert swell.height == pytest.approx(1.82)
        assert swell.period is None
        assert swell.direction is None

    def test_wind_fields_mapped_correctly(self, result):
        point = result.forecast[0]
        assert point.wind is not None
        assert point.wind.speed == pytest.approx(5.52)
        assert point.wind.direction == pytest.approx(45.2)

    def test_tide_height_from_zos(self, result):
        assert result.forecast[0].tide is not None
        assert result.forecast[0].tide.height == pytest.approx(0.28)


@pytest.mark.unit
class TestNWPSMetadata:
    def test_provider_and_model(self, result):
        assert result.provider == ForecastProvider.NOMADS
        assert result.model == ForecastModel.NWPS

    def test_region_and_spot_id(self, result, raw_nwps_data):
        assert result.region == Region.MAUI
        assert result.spot_id == 1

    def test_analysis_time_preserved(self, result, raw_nwps_data):
        assert result.analysis_time == raw_nwps_data["analysis_time"]

    def test_grid_metadata_preserved(self, result, raw_nwps_data):
        meta = raw_nwps_data["grid_metadata"]
        assert result.grid_metadata.selected_lat == meta["selected_lat"]
        assert result.grid_metadata.selected_lon == meta["selected_lon"]
        assert result.grid_metadata.distance_km == meta["distance_km"]

    def test_forecast_length_matches_valid_times(self, result, raw_nwps_data):
        assert len(result.forecast) == len(raw_nwps_data["valid_times"])
