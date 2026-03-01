from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from schemas.condition_profile_schema import (
    ProviderConditionEntry,
    RangeCondition,
    DirectionRangeCondition,
    WaveConditions,
    WindConditions,
    TideConditions,
    SwellConditions,
)
from services.condition_profile_service import ConditionProfileService
from services.forecast.forecast_schema import (
    ForecastPoint,
    SwellPartition,
    TideData,
    WaveData,
    WindData,
)


@pytest.fixture
def service():
    """Bare service with no deps — only pure methods are callable."""
    return ConditionProfileService(None, None, None, None, None, None)  # type: ignore[non-args]


@pytest.fixture
def now():
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_point(valid_time: datetime, wave=None, wind=None, tide=None) -> ForecastPoint:
    return ForecastPoint(valid_time=valid_time, wave=wave, wind=wind, tide=tide)


def make_wave_entry(
    sig_height=None, peak_period=None, peak_direction=None, primary_swell=None
) -> ProviderConditionEntry:
    return ProviderConditionEntry(
        provider="nomads",
        model="nwps",
        wave=WaveConditions(
            significant_height=sig_height,
            peak_period=peak_period,
            peak_direction=peak_direction,
            primary_swell=primary_swell,
        ),
    )


def make_wind_entry(speed=None, direction=None) -> ProviderConditionEntry:
    return ProviderConditionEntry(
        provider="nomads",
        model="nwps",
        wind=WindConditions(speed=speed, direction=direction),
    )


def make_tide_entry(height=None) -> ProviderConditionEntry:
    return ProviderConditionEntry(
        provider="pacioos",
        model="tide_mhi",
        tide=TideConditions(height=height),
    )


def mock_profile(spot_id: int, conditions: list[dict]):
    """Lightweight stand-in for ConditionProfile ORM object."""
    return SimpleNamespace(spot_id=spot_id, id=1, name="Test", conditions=conditions)


@pytest.mark.unit
class TestFindNearestForecastPoint:
    def test_empty_list_returns_none(self, service, now):
        assert service._find_nearest_forecast_point([], now) is None

    def test_selects_closest_to_now(self, service, now):
        points = [
            make_point(now - timedelta(hours=3)),
            make_point(now - timedelta(hours=1)),  # closest
            make_point(now + timedelta(hours=5)),
        ]
        result = service._find_nearest_forecast_point(points, now)
        assert result is not None
        assert result.valid_time == now - timedelta(hours=1)

    def test_abs_distance_past_and_future_equal(self, service, now):
        one_hour_ago = make_point(now - timedelta(hours=1))
        one_hour_ahead = make_point(now + timedelta(hours=1))
        result = service._find_nearest_forecast_point(
            [one_hour_ago, one_hour_ahead], now
        )

        # both are equidistant. either is valid, just not None
        assert result is not None
        assert abs(result.valid_time - now) == timedelta(hours=1)


@pytest.mark.unit
class TestEntryMatches:
    def test_wave_height_in_range(self, service, now):
        entry = make_wave_entry(sig_height=RangeCondition(min=1.0, max=3.0))
        point = make_point(now, wave=WaveData(significant_height=2.1))
        assert service._entry_matches(entry, point) is True

    def test_wave_height_out_of_range(self, service, now):
        entry = make_wave_entry(sig_height=RangeCondition(min=1.0, max=3.0))
        point = make_point(now, wave=WaveData(significant_height=4.5))
        assert service._entry_matches(entry, point) is False

    def test_wave_condition_but_no_wave_data(self, service, now):
        entry = make_wave_entry(sig_height=RangeCondition(min=1.0, max=3.0))
        point = make_point(now, wave=None)
        assert service._entry_matches(entry, point) is False

    def test_wind_speed_in_range(self, service, now):
        entry = make_wind_entry(speed=RangeCondition(max=5.0))
        point = make_point(now, wind=WindData(speed=3.5))
        assert service._entry_matches(entry, point) is True

    def test_wind_speed_out_of_range(self, service, now):
        entry = make_wind_entry(speed=RangeCondition(max=5.0))
        point = make_point(now, wind=WindData(speed=8.0))
        assert service._entry_matches(entry, point) is False

    def test_tide_height_in_range(self, service, now):
        entry = make_tide_entry(height=RangeCondition(min=0.0, max=0.5))
        point = make_point(now, tide=TideData(height=0.3))
        assert service._entry_matches(entry, point) is True

    def test_multiple_conditions_all_match(self, service, now):
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(significant_height=RangeCondition(min=1.0, max=3.0)),
            wind=WindConditions(speed=RangeCondition(max=5.0)),
        )
        point = make_point(
            now,
            wave=WaveData(significant_height=2.0),
            wind=WindData(speed=4.0),
        )
        assert service._entry_matches(entry, point) is True

    def test_multiple_conditions_one_fails(self, service, now):
        entry = ProviderConditionEntry(
            provider="nomads",
            model="nwps",
            wave=WaveConditions(significant_height=RangeCondition(min=1.0, max=3.0)),
            wind=WindConditions(speed=RangeCondition(max=5.0)),
        )
        point = make_point(
            now,
            wave=WaveData(significant_height=2.0),
            wind=WindData(speed=9.0),  # exceeds max
        )
        assert service._entry_matches(entry, point) is False

    def test_primary_swell_matches(self, service, now):
        entry = make_wave_entry(
            primary_swell=SwellConditions(
                height=RangeCondition(min=1.0, max=2.5),
                direction=DirectionRangeCondition(min=270.0, max=360.0),
            )
        )
        point = make_point(
            now,
            wave=WaveData(
                significant_height=2.1,
                primary_swell=SwellPartition(height=1.8, direction=315.0),
            ),
        )
        assert service._entry_matches(entry, point) is True

    def test_primary_swell_missing_from_forecast(self, service, now):
        entry = make_wave_entry(
            primary_swell=SwellConditions(height=RangeCondition(min=1.0, max=3.0))
        )
        point = make_point(
            now, wave=WaveData(significant_height=2.1, primary_swell=None)
        )
        assert service._entry_matches(entry, point) is False


# ============================================================================
# Tests: _evaluate_profile
# ============================================================================


@pytest.mark.unit
class TestEvaluateProfile:
    # TODO(human): Implement these tests.
    #
    # _evaluate_profile(profile, forecast_lookup) does AND logic across all
    # provider+model entries in a profile's conditions list.
    #
    # The profile is a mock object with:
    #   - profile.spot_id: int
    #   - profile.conditions: list[dict]  ← raw JSONB dicts, not Pydantic objects
    #
    # The forecast_lookup is a flat dict keyed by (spot_id, provider, model):
    #   {(1, "nomads", "nwps"): ForecastPoint, (1, "pacioos", "tide_mhi"): None}
    #
    # Tests to implement (see TEST_PLAN for descriptions):
    #   - test_single_entry_matches
    #   - test_missing_forecast_data_returns_false   ← key not in lookup at all
    #   - test_and_across_providers                  ← two providers, both match
    #   - test_and_across_providers_one_fails        ← two providers, one misses
    #   - test_none_forecast_point_in_lookup         ← key exists but value is None
    #
    # Hint: use mock_profile() and the condition dicts should look like:
    #   {"provider": "nomads", "model": "nwps", "wave": {"significant_height": {"min": 1.0}}}
    pass
