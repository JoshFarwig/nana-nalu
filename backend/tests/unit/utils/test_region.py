import pytest

from utils.region import RegionGrid, Region, load_regions


@pytest.fixture
def maui_grid():
    return RegionGrid(
        lat_min=20.553, lat_max=21.042, long_min=-156.720, long_max=-155.954
    )


@pytest.mark.unit
class TestRegionGridContains:
    def test_point_inside_grid(self, maui_grid):
        assert maui_grid.contains(20.8, -156.3) is True

    def test_point_outside_lat(self, maui_grid):
        assert maui_grid.contains(19.0, -156.3) is False

    def test_point_outside_lon(self, maui_grid):
        assert maui_grid.contains(20.8, -157.0) is False

    def test_point_on_lat_boundary(self, maui_grid):
        assert maui_grid.contains(20.553, -156.3) is True
        assert maui_grid.contains(21.042, -156.3) is True

    def test_point_on_lon_boundary(self, maui_grid):
        assert maui_grid.contains(20.8, -156.720) is True
        assert maui_grid.contains(20.8, -155.954) is True


@pytest.mark.unit
class TestLoadRegions:
    def test_valid_region_string(self):
        result = load_regions("maui")
        assert result == {Region.MAUI}

    def test_case_insensitive(self):
        assert load_regions("MAUI") == {Region.MAUI}
        assert load_regions("Maui") == {Region.MAUI}

    def test_empty_string_defaults_to_maui(self):
        result = load_regions("")
        assert result == {Region.MAUI}

    def test_all_invalid_defaults_to_maui(self):
        result = load_regions("atlantis,narnia")
        assert result == {Region.MAUI}

    def test_partial_valid_keeps_valid_drops_invalid(self):
        result = load_regions("maui,atlantis")
        assert Region.MAUI in result
        assert len(result) == 1
