from pydantic import ValidationError
import pytest

from schemas.condition_profile_schema import (
    RangeCondition,
    DirectionRangeCondition,
    WaveConditions,
    WindConditions,
    TideConditions,
    ProviderConditionEntry,
    ConditionProfileCreate,
    ConditionProfileUpdate,
    in_range,
    direction_in_range,
)


@pytest.fixture
def standard_range():
    return RangeCondition(min=28.0, max=35.0)


@pytest.fixture
def min_only():
    return RangeCondition(min=30.0)


@pytest.fixture
def max_only():
    return RangeCondition(max=60.0)


@pytest.fixture
def equals_range():
    return RangeCondition(min=315.0, max=315.0)


@pytest.fixture
def north_crossing_directional_range():
    return DirectionRangeCondition(min=330.0, max=30.0)


@pytest.fixture
def provider_condition_entry():
    return ProviderConditionEntry(
        provider="test",
        model="test",
        wave=WaveConditions(significant_height=RangeCondition(min=2)),
    )


@pytest.mark.unit
class TestRangeCondition:
    def test_atleast_one_bound(self):
        with pytest.raises(ValidationError):
            RangeCondition()

    def test_min_gt_max_rejected(self):
        with pytest.raises(ValidationError):
            RangeCondition(min=10.0, max=5.0)


@pytest.mark.unit
class TestDirectionRangeCondition:
    def test_valid_bounds(self):
        assert DirectionRangeCondition(min=0.0, max=360.0)

    def test_north_crossing_valid(self):
        assert DirectionRangeCondition(min=330.0, max=30.0)

    def test_min_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            DirectionRangeCondition(min=-1.0)

    def test_max_above_360_rejected(self):
        with pytest.raises(ValidationError):
            DirectionRangeCondition(max=361.0)


@pytest.mark.unit
class TestInRange:
    def test_value_within_range(self, standard_range):
        assert in_range(30.0, standard_range) is True

    def test_value_at_min_bound(self, standard_range):
        assert in_range(28.0, standard_range) is True

    def test_value_at_max_bound(self, standard_range):
        assert in_range(35.0, standard_range) is True

    def test_value_below_min(self, standard_range):
        assert in_range(20.0, standard_range) is False

    def test_value_above_max(self, standard_range):
        assert in_range(40.0, standard_range) is False

    def test_none_value_always_false(self, standard_range):
        assert in_range(None, standard_range) is False

    def test_min_only(self, min_only):
        assert in_range(60.0, min_only) is True
        assert in_range(0.0, min_only) is False

    def test_max_only(self, max_only):
        assert in_range(30.0, max_only) is True
        assert in_range(90.0, max_only) is False

    def test_exact_value(self, equals_range):
        assert in_range(315.0, equals_range) is True
        assert in_range(300, equals_range) is False


@pytest.mark.unit
class TestDirectionInRange:
    def test_value_within_range(self, standard_range):
        assert direction_in_range(30.0, standard_range) is True

    def test_value_at_min_bound(self, standard_range):
        assert direction_in_range(28.0, standard_range) is True

    def test_value_at_max_bound(self, standard_range):
        assert direction_in_range(35.0, standard_range) is True

    def test_value_below_min(self, standard_range):
        assert direction_in_range(20.0, standard_range) is False

    def test_value_above_max(self, standard_range):
        assert direction_in_range(40.0, standard_range) is False

    def test_none_value_always_false(self, standard_range):
        assert direction_in_range(None, standard_range) is False

    def test_min_only(self, min_only):
        assert direction_in_range(60.0, min_only) is True
        assert direction_in_range(0.0, min_only) is False

    def test_max_only(self, max_only):
        assert direction_in_range(30.0, max_only) is True
        assert direction_in_range(90.0, max_only) is False

    def test_exact_value(self, equals_range):
        assert direction_in_range(315.0, equals_range) is True
        assert direction_in_range(300, equals_range) is False

    def test_north_wrap_inside_high_side(self, north_crossing_directional_range):
        assert direction_in_range(350.0, north_crossing_directional_range) is True

    def test_north_wrap_inside_low_side(self, north_crossing_directional_range):
        assert direction_in_range(10.0, north_crossing_directional_range) is True

    def test_north_wrap_outside(self, north_crossing_directional_range):
        assert direction_in_range(180.0, north_crossing_directional_range) is False

    def test_north_wrap_boundary(self, north_crossing_directional_range):
        assert direction_in_range(330.0, north_crossing_directional_range) is True
        assert direction_in_range(30.0, north_crossing_directional_range) is True


@pytest.mark.unit
class TestProviderConditionEntry:
    def test_atleast_one_condition(self):
        with pytest.raises(ValidationError):
            ProviderConditionEntry(
                provider="test", model="test", wave=None, wind=None, tide=None
            )


@pytest.mark.unit
class TestConditionProfileCreate:
    def test_valid_multi_provider_profile(self):
        profile = ConditionProfileCreate(
            name="Maui NW swell + offshore wind",
            conditions=[
                ProviderConditionEntry(
                    provider="nomads",
                    model="nwps",
                    wave=WaveConditions(
                        significant_height=RangeCondition(min=1.5, max=4.0),
                        primary_swell=None,
                    ),
                    wind=WindConditions(speed=RangeCondition(max=5.0)),
                ),
                ProviderConditionEntry(
                    provider="pacioos",
                    model="tide_mhi",
                    tide=TideConditions(height=RangeCondition(min=0.0, max=0.5)),
                ),
            ],
        )
        assert profile.name == "Maui NW swell + offshore wind"
        assert len(profile.conditions) == 2

    def test_no_empty_conditions_list(self):
        with pytest.raises(ValidationError):
            ConditionProfileCreate(name="Test no list", conditions=[])

    def test_no_duplicate_provider_model(self, provider_condition_entry):
        with pytest.raises(ValidationError):
            ConditionProfileCreate(
                name="Test duplicate entries",
                conditions=[provider_condition_entry, provider_condition_entry],
            )


@pytest.mark.unit
class TestConditionProfileUpdate:
    def test_no_none_or_empty_conditions(self):
        with pytest.raises(ValidationError):
            ConditionProfileUpdate(name="Test no none conditions", conditions=None)

        with pytest.raises(ValidationError):
            ConditionProfileUpdate(name="Test no empty conditions", conditions=[])

    def test_no_duplicate_provider_model(self, provider_condition_entry):
        with pytest.raises(ValidationError):
            ConditionProfileUpdate(
                name="Test duplicate entries",
                conditions=[provider_condition_entry, provider_condition_entry],
            )
