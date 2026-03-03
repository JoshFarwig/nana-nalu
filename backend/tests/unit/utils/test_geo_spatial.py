import numpy as np
import pytest
from scipy.spatial import cKDTree

from utils.geo_spatial import query_nearest_forecast_points


@pytest.fixture
def two_point_grid():
    """Minimal 2-node KDTree near Maui"""
    lats = np.array([20.0, 21.0], dtype=float)
    lons = np.array([-156.0, -155.0], dtype=float)
    coords_rad = np.column_stack([np.radians(lats), np.radians(lons)])
    tree = cKDTree(coords_rad)
    return tree, lats, lons


@pytest.mark.unit
class TestQueryNearestForecastPoints:
    def test_within_threshold_returns_valid_coords(self, two_point_grid):
        tree, valid_lats, valid_lons = two_point_grid
        selected_lats, selected_lons, _ = query_nearest_forecast_points(
            tree,
            valid_lats,
            valid_lons,
            target_lats=np.array([20.01]),
            target_lons=np.array([-156.01]),
            max_distance_km=10.0,
        )
        assert not np.isnan(selected_lats[0])
        assert not np.isnan(selected_lons[0])
        assert selected_lats[0] == pytest.approx(20.0)

    def test_beyond_threshold_returns_nan(self, two_point_grid):
        tree, valid_lats, valid_lons = two_point_grid
        selected_lats, selected_lons, _ = query_nearest_forecast_points(
            tree,
            valid_lats,
            valid_lons,
            target_lats=np.array([10.0]),
            target_lons=np.array([-140.0]),
            max_distance_km=100.0,
        )
        assert np.isnan(selected_lats[0])
        assert np.isnan(selected_lons[0])

    def test_no_threshold_always_returns_coords(self, two_point_grid):
        tree, valid_lats, valid_lons = two_point_grid
        selected_lats, selected_lons, _ = query_nearest_forecast_points(
            tree,
            valid_lats,
            valid_lons,
            target_lats=np.array([10.0]),
            target_lons=np.array([-140.0]),
            max_distance_km=None,
        )
        assert not np.isnan(selected_lats[0])
        assert not np.isnan(selected_lons[0])

    def test_distances_returned_in_km_not_radians(self, two_point_grid):
        tree, valid_lats, valid_lons = two_point_grid
        _, _, distances = query_nearest_forecast_points(
            tree,
            valid_lats,
            valid_lons,
            target_lats=np.array([20.01]),
            target_lons=np.array([-156.01]),
        )
        assert 0.5 < distances[0] < 10.0
