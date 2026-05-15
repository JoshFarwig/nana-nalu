from datetime import datetime, timezone

import pytest

from domain.models import PacIOOSModel
from domain.provider import ForecastProvider
from utils.region import Region
from workflows.pacioos.mapper import map_pacioos_tide_forecast


@pytest.fixture
def raw_tide_data():
    return {
        "valid_times": [
            datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
        ],
        "data": {
            "ssh": [0.2847, -0.1432],
        },
        "grid_metadata": {
            "selected_lat": 20.8,
            "selected_lon": -156.3,
            "distance_km": 1.5,
        },
    }


@pytest.fixture
def result(raw_tide_data):
    return map_pacioos_tide_forecast(
        spot_id=1,
        region=Region.MAUI,
        raw_data=raw_tide_data,
        data_summary={"tide": "Astronomical tidal predictions"},
    )


@pytest.mark.unit
class TestPacIOOSTideMetadata:
    def test_provider_and_model(self, result):
        assert result.provider == ForecastProvider.PACIOOS
        assert result.model == PacIOOSModel.TIDE_MHI

    def test_forecast_length_matches_valid_times(self, result, raw_tide_data):
        assert len(result.forecast) == len(raw_tide_data["valid_times"])

    def test_grid_metadata_preserved(self, result, raw_tide_data):
        meta = raw_tide_data["grid_metadata"]
        assert result.grid_metadata.selected_lat == meta["selected_lat"]
        assert result.grid_metadata.selected_lon == meta["selected_lon"]
        assert result.grid_metadata.distance_km == meta["distance_km"]


@pytest.mark.unit
class TestPacIOOSTideFieldMapping:
    pass
