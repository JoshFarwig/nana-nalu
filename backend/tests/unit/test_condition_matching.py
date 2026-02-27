"""
Unit tests for condition profile matching logic.

Tests the pure-function matching pipeline:
  in_range / direction_in_range → _entry_matches → _evaluate_profile

No external services — all forecast data constructed in-memory.
"""

import pytest
from datetime import datetime, timezone

from schemas.condition_profile_schema import (
    RangeCondition,
    in_range,
    direction_in_range,
    ProviderConditionEntry,
    WaveConditions,
    WindConditions,
    TideConditions,
    SwellConditions,
)

from services.forecast.forecast_schema import (
    ForecastPoint,
    WaveData,
    WindData,
    TideData,
    SwellPartition,
)

from services.condition_profile_service import ConditionProfileService


class TestInRange:
    def test_value_within_range(self):
        assert in_range(5.0, RangeCondition(min=2.0, max=8.0)) is True

    def test_value_at_min_boundary(self):
        assert in_range(2.0, RangeCondition(min=2.0, max=8.0)) is True

    def test_value_at_max_boundary(self):
        assert in_range(8.0, RangeCondition(min=2.0, max=8.0)) is True

    def test_value_below_min(self):
        assert in_range(1.0, RangeCondition(min=2.0, max=8.0)) is False

    def test_value_above_max(self):
        assert in_range(9.0, RangeCondition(min=2.0, max=8.0)) is False

    def test_none_value_always_false(self):
        assert in_range(None, RangeCondition(min=2.0, max=8.0)) is False

    def test_min_only(self):
        assert in_range(10.0, RangeCondition(min=2.0)) is True
        assert in_range(1.0, RangeCondition(min=2.0)) is False

    def test_max_only(self):
        assert in_range(3.0, RangeCondition(max=8.0)) is True
        assert in_range(9.0, RangeCondition(max=8.0)) is False

    def test_exact_value(self):
        assert in_range(5.0, RangeCondition(min=5.0, max=5.0)) is True
        assert in_range(5.1, RangeCondition(min=5.0, max=5.0)) is False


class TestDirectionInRange:
    def test_normal_range(self):
        assert direction_in_range(180.0, RangeCondition(min=90.0, max=270.0)) is True
        assert direction_in_range(90.0, RangeCondition(min=90.0, max=270.0)) is True
        assert direction_in_range(270.0, RangeCondition(min=90.0, max=270.0)) is True

    def test_outside_normal_range(self):
        assert direction_in_range(45.0, RangeCondition(min=90.0, max=270.0)) is False

    def test_none_value_always_false(self):
        assert direction_in_range(None, RangeCondition(min=90.0, max=270.0)) is False

    def test_min_only_direction(self):
        assert direction_in_range(350.0, RangeCondition(min=300.0)) is True
        assert direction_in_range(300.0, RangeCondition(min=300.0)) is True
        assert direction_in_range(290.0, RangeCondition(min=300.0)) is False

    def test_max_only_direction(self):
        assert direction_in_range(20.0, RangeCondition(max=90.0)) is True
        assert direction_in_range(90.0, RangeCondition(max=90.0)) is True
        assert direction_in_range(100.0, RangeCondition(max=90.0)) is False

    def test_north_crossing_range(self):
        north_crossing_range = RangeCondition(min=330.0, max=30.0)
        assert direction_in_range(350.0, north_crossing_range) is True
        assert direction_in_range(10.0, north_crossing_range) is True
        assert direction_in_range(330.0, north_crossing_range) is True
        assert direction_in_range(30.0, north_crossing_range) is True
        assert direction_in_range(180.0, north_crossing_range) is False


class TestEntryMatches:
    @pytest.fixture
    def service(self):
        return ConditionProfileService(
            forecast_service=None,
            profile_repo=None,
            spot_repo=None,
            profile_policy=None,
            spot_policy=None,
            session=None,
        )

    def test_wave_height_in_range(self, service, typical_wave_point):
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(significant_height=RangeCondition(min=1.0, max=3.0)),
        )
        assert service._entry_matches(entry, typical_wave_point) is True

    def test_wave_height_out_of_range(self, service, typical_wave_point):
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(significant_height=RangeCondition(min=5.0, max=10.0)),
        )
        assert service._entry_matches(entry, typical_wave_point) is False

    def test_wind_speed_in_range(self, service, typical_wave_point):
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wind=WindConditions(speed=RangeCondition(max=10.0)),
        )
        assert service._entry_matches(entry, typical_wave_point) is True

    def test_wind_speed_out_of_range(self, service, typical_wave_point):
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wind=WindConditions(speed=RangeCondition(max=3.0)),
        )
        assert service._entry_matches(entry, typical_wave_point) is False

    def test_tide_height_in_range(self, service, typical_wave_point):
        entry = ProviderConditionEntry(
            provider="pacioos",
            model="tide",
            tide=TideConditions(height=RangeCondition(min=-0.5, max=0.5)),
        )
        assert service._entry_matches(entry, typical_wave_point) is True

    def test_multiple_conditions_all_must_match(self, service, typical_wave_point):
        """AND logic: wave matches but wind doesn't → False."""
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(significant_height=RangeCondition(min=1.0, max=3.0)),
            wind=WindConditions(speed=RangeCondition(max=2.0)),  # 5.5 > 2.0 → miss
        )
        assert service._entry_matches(entry, typical_wave_point) is False

    def test_multiple_conditions_all_match(self, service, typical_wave_point):
        """AND logic: everything matches → True."""
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(significant_height=RangeCondition(min=1.0, max=3.0)),
            wind=WindConditions(speed=RangeCondition(max=10.0)),
            tide=TideConditions(height=RangeCondition(min=-1.0, max=1.0)),
        )
        assert service._entry_matches(entry, typical_wave_point) is True

    def test_wave_condition_but_no_wave_data(self, service, make_forecast_point):
        """Entry expects wave data, but forecast has none → False."""
        point = make_forecast_point(wind={"speed": 5.0, "direction": 90.0})
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(significant_height=RangeCondition(min=1.0)),
        )
        assert service._entry_matches(entry, point) is False

    def test_primary_swell_matches(self, service, typical_wave_point):
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(
                primary_swell=SwellConditions(
                    height=RangeCondition(min=1.0, max=3.0),
                    period=RangeCondition(min=12.0),
                ),
            ),
        )
        # primary_swell: height=1.8, period=15.0 → both match
        assert service._entry_matches(entry, typical_wave_point) is True

    def test_primary_swell_missing_from_forecast(self, service, make_forecast_point):
        """Entry expects primary swell but forecast has no swell data."""
        point = make_forecast_point(
            wave={"significant_height": 2.0, "peak_period": 10.0},
        )
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(
                primary_swell=SwellConditions(height=RangeCondition(min=1.0)),
            ),
        )
        assert service._entry_matches(entry, point) is False

    def test_secondary_swell_out_of_range(self, service, typical_wave_point):
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(
                secondary_swell=SwellConditions(
                    height=RangeCondition(min=2.0),  # secondary is 0.6 → miss
                ),
            ),
        )
        assert service._entry_matches(entry, typical_wave_point) is False


class TestEvaluateProfile:
    @pytest.fixture
    def service(self):
        return ConditionProfileService(
            forecast_service=None,
            profile_repo=None,
            spot_repo=None,
            profile_policy=None,
            spot_policy=None,
            session=None,
        )

    @pytest.fixture
    def mock_profile(self):
        class FakeProfile:
            def __init__(self, spot_id, conditions):
                self.id = 1
                self.spot_id = spot_id
                self.name = "test profile"
                self.user_id = 1
                self.conditions = conditions

        return FakeProfile

    def test_single_entry_matches(self, service, mock_profile, typical_wave_point):
        profile = mock_profile(
            spot_id=1,
            conditions=[
                {
                    "provider": "nomads",
                    "model": "nwps",
                    "wave": {"significant_height": {"min": 1.0, "max": 3.0}},
                }
            ],
        )
        lookup = {(1, "nomads", "nwps"): typical_wave_point}
        assert service._evaluate_profile(profile, lookup) is True

    def test_missing_forecast_data_returns_false(self, service, mock_profile):
        """Provider data not in lookup → can't confirm → False."""
        profile = mock_profile(
            spot_id=1,
            conditions=[
                {
                    "provider": "nomads",
                    "model": "nwps",
                    "wave": {"significant_height": {"min": 1.0}},
                }
            ],
        )
        lookup = {}  # empty — no forecast data available
        assert service._evaluate_profile(profile, lookup) is False

    def test_and_across_providers(
        self, service, mock_profile, typical_wave_point, make_forecast_point
    ):
        """Two entries (different providers) must ALL match."""
        tide_point = make_forecast_point(tide={"height": 0.3})

        profile = mock_profile(
            spot_id=1,
            conditions=[
                {
                    "provider": "nomads",
                    "model": "nwps",
                    "wave": {"significant_height": {"min": 1.0, "max": 3.0}},
                },
                {
                    "provider": "pacioos",
                    "model": "tide",
                    "tide": {"height": {"min": -0.5, "max": 0.5}},
                },
            ],
        )
        lookup = {
            (1, "nomads", "nwps"): typical_wave_point,
            (1, "pacioos", "tide"): tide_point,
        }
        assert service._evaluate_profile(profile, lookup) is True

    def test_and_across_providers_one_fails(
        self, service, mock_profile, typical_wave_point, make_forecast_point
    ):
        """One provider matches, other doesn't → False."""
        tide_point = make_forecast_point(tide={"height": 1.5})  # too high

        profile = mock_profile(
            spot_id=1,
            conditions=[
                {
                    "provider": "nomads",
                    "model": "nwps",
                    "wave": {"significant_height": {"min": 1.0, "max": 3.0}},
                },
                {
                    "provider": "pacioos",
                    "model": "tide",
                    "tide": {"height": {"max": 0.5}},  # 1.5 > 0.5 → miss
                },
            ],
        )
        lookup = {
            (1, "nomads", "nwps"): typical_wave_point,
            (1, "pacioos", "tide"): tide_point,
        }
        assert service._evaluate_profile(profile, lookup) is False

    def test_none_forecast_point_in_lookup(self, service, mock_profile):
        """Lookup has the key but value is None (Redis miss) → False."""
        profile = mock_profile(
            spot_id=1,
            conditions=[
                {
                    "provider": "nomads",
                    "model": "nwps",
                    "wave": {"significant_height": {"min": 1.0}},
                }
            ],
        )
        lookup = {(1, "nomads", "nwps"): None}
        assert service._evaluate_profile(profile, lookup) is False
