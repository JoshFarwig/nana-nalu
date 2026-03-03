import pytest

from utils.geo_validation import (
    longitude_to_360,
    longitude_to_180,
    valid_longitude,
    valid_latitude,
)


@pytest.mark.unit
class TestLongitudeTo360:
    def test_maui_longitude_converts_correctly(self):
        assert longitude_to_360(-157.8, 4) == 202.2

    def test_positive_longitude_is_passthrough(self):
        assert longitude_to_360(10.0, 1) == 10.0

    def test_zero_longitude_unchanged(self):
        assert longitude_to_360(0.0, 1) == 0.0

    def test_negative_180_converts_to_180(self):
        assert longitude_to_360(-180.0, 1) == 180.0

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            longitude_to_360(-181.0, 4)


@pytest.mark.unit
class TestLongitudeTo180:
    def test_maui_360_space_converts_back(self):
        assert longitude_to_180(202.2, 4) == -157.8

    def test_zero_unchanged(self):
        assert longitude_to_180(0.0, 1) == 0.0

    def test_round_trip(self):
        original = -157.8
        in_360 = longitude_to_360(original, 4)
        result = longitude_to_180(in_360, 4)
        assert abs(result - original) < 1e-6

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            longitude_to_180(361.0, 4)


@pytest.mark.unit
class TestValidLongitude:
    def test_signed_boundaries_valid(self):
        assert valid_longitude(-180.0, "signed") is True
        assert valid_longitude(180.0, "signed") is True

    def test_signed_zero_valid(self):
        assert valid_longitude(0.0, "signed") is True

    def test_signed_outside_range_invalid(self):
        assert valid_longitude(-181.0, "signed") is False
        assert valid_longitude(181.0, "signed") is False

    def test_unsigned_boundaries_valid(self):
        assert valid_longitude(0.0, "unsigned") is True
        assert valid_longitude(360.0, "unsigned") is True

    def test_unsigned_outside_range_invalid(self):
        assert valid_longitude(-1.0, "unsigned") is False
        assert valid_longitude(361.0, "unsigned") is False


@pytest.mark.unit
class TestValidLatitude:
    def test_boundaries_valid(self):
        assert valid_latitude(-90.0) is True
        assert valid_latitude(90.0) is True

    def test_zero_valid(self):
        assert valid_latitude(0.0) is True

    def test_outside_range_invalid(self):
        assert valid_latitude(-91.0) is False
        assert valid_latitude(91.0) is False
