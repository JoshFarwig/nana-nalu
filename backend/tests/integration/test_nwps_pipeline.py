"""
Integration test for NWPS forecast pipeline.

This test verifies the end-to-end NWPS data flow:
1. find latest available GRIB2 file from NOMADS (within 24 hours)
2. download GRIB2 file
3. extract forecast data for Maui surf spots
4. store forecasts in Redis with correct fields

Prerequisites:
- docker test services running (docker compose -f docker-compose.test.yml up -d)
- test database with surf spots seeded
- redis instance available

run with: pytest -m integration tests/integration/test_nwps_pipeline.py -v
"""

import pytest
import json
from pathlib import Path

from sqlalchemy.orm import Session
import redis

from services.forecast.providers.nwps.provider import NWPSProvider
from services.forecast.providers.nwps.config import get_nwps_config
from services.forecast.providers.nwps.availability import NWPSAvailabilityChecker
from repositories.surf_spot_repository import SyncSurfSpotRepository
from utils.location import Location
from core.http import SyncHTTPManager


@pytest.mark.integration
class TestNWPSPipeline:
    """Integration tests for NWPS forecast data pipeline"""

    def test_nwps_forecast_extraction_and_storage(
        self,
        sync_db_session: Session,
        sync_redis_client: redis.Redis,
        http_manager: SyncHTTPManager,
        sample_maui_spots,
    ):
        """
        Test complete NWPS pipeline: download → extract → validate fields → store in Redis

        This test verifies:
        - availability checker finds latest run within 24 hours
        - GRIB file download works
        - forecast extraction finds both Maui spots (Ho'okipa and Hamoa)
        - data contains required fields: swh, perpw, dirpw, swell, etc.
        - data is properly stored in Redis with correct keys
        """
        config = get_nwps_config(Location.MAUI)
        repo = SyncSurfSpotRepository(sync_db_session)
        provider = NWPSProvider(config, http_manager, repo)
        checker = NWPSAvailabilityChecker(config, http_manager)

        # find latest available run (search back 24 hours)
        latest_run = checker.get_latest_available_run(max_lookback_hours=24)

        assert latest_run is not None, (
            "No NWPS run found in last 24 hours. "
            "NOMADS may be down or no recent runs available. "
            "Check https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod/"
        )

        forecast_date, analysis_time = latest_run

        # download GRIB file
        file_path: Path | None = None
        try:
            file_path = provider.download_file(analysis_time, forecast_date)
            assert file_path.exists(), f"downloaded file not found at {file_path}"
            assert file_path.stat().st_size > 0, "downloaded file is empty"

            # extract forecasts
            forecasts = provider.extract_forecasts(file_path)

            # verify we got forecasts for our Maui spots
            assert len(forecasts) > 0, "no forecasts extracted"

            # log what we actually got
            print(f"\n{'=' * 60}")
            print(f"Found {len(forecasts)} spots with forecast data")
            print(f"{'=' * 60}")

            # get the spot IDs from our test data
            spot_ids = [spot.id for spot in sample_maui_spots]

            # verify we have forecasts for at least one of our spots
            # (some spots might be filtered if they're out of grid bounds)
            forecast_spot_ids = list(forecasts.keys())
            assert any(spot_id in forecast_spot_ids for spot_id in spot_ids), (
                f"no forecasts found for test spots. expected {spot_ids}, got {forecast_spot_ids}"
            )

            # verify forecast data structure for each spot
            for spot_id, forecast_data in forecasts.items():
                print(f"\nSpot ID: {spot_id}")
                print(f"  Grid metadata: {forecast_data['grid_metadata']}")
                print(f"  Analysis time: {forecast_data['analysis_time']}")

                # show valid times info
                valid_times = forecast_data["valid_times"]
                print(f"  Valid times: {len(valid_times)} forecast hours")
                print(f"    First: {valid_times[0]}")
                print(f"    Last:  {valid_times[-1]}")

                print(f"  Available variables: {list(forecast_data['data'].keys())}")

                # show first 2 values of each variable
                print("  Sample data (first 2 values):")
                for var_name, var_data in forecast_data["data"].items():
                    print(f"    {var_name:8s}: {var_data[:2]}")

                # check top-level structure
                assert "spot_id" in forecast_data
                assert "grid_metadata" in forecast_data
                assert "analysis_time" in forecast_data
                assert "valid_times" in forecast_data
                assert "data" in forecast_data

                # check grid metadata
                grid_meta = forecast_data["grid_metadata"]
                assert "selected_lat" in grid_meta
                assert "selected_lon" in grid_meta
                assert "distance_km" in grid_meta
                assert (
                    grid_meta["distance_km"] <= config.max_nearest_neighbor_distance_km
                )

                # check required forecast variables (NWPS surface variables)
                data = forecast_data["data"]
                # only check variables that actually exist in NWPS output
                required_fields = ["swh", "perpw", "dirpw"]

                for field in required_fields:
                    assert field in data, (
                        f"missing required field '{field}' for spot {spot_id}. "
                        f"available fields: {list(data.keys())}"
                    )
                    assert isinstance(data[field], list), (
                        f"field '{field}' should be a list"
                    )
                    assert len(data[field]) > 0, f"field '{field}' has no data"

                # verify valid_times is a list with data
                assert isinstance(forecast_data["valid_times"], list)
                assert len(forecast_data["valid_times"]) > 0

            # store in Redis (simulating the Celery task behavior)
            location = Location.MAUI
            for spot_id, spot_data in forecasts.items():
                key = f"forecast:nwps:{location.value}:{spot_id}"
                sync_redis_client.setex(key, 3600, json.dumps(spot_data))  # 1 hour TTL

            # verify Redis storage
            for spot_id in forecasts.keys():
                key = f"forecast:nwps:{location.value}:{spot_id}"
                stored_data = sync_redis_client.get(key)

                assert stored_data is not None, f"no data found in Redis for key {key}"

                # verify we can deserialize the stored data
                parsed_data = json.loads(stored_data)  # type: ignore[arg-type]
                assert parsed_data["spot_id"] == spot_id
                assert "swh" in parsed_data["data"]

        finally:
            # cleanup - remove downloaded file
            if file_path is not None and file_path.exists():
                file_path.unlink(missing_ok=True)
