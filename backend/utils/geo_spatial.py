"""
Spatial operations for forecast data using KDTree for nearest neighbor search.
Requires numpy, scipy, and xarray - only used in worker containers.
"""
from typing import Any
import logging

import numpy as np
import xarray as xr
from scipy.spatial import cKDTree

from utils.geo_validation import EARTH_MEAN_RADIUS_KM

logger = logging.getLogger(__name__)


def build_forecast_kdtree(
    ds: xr.Dataset, valid_var: str, time_slice: dict[str, Any]
) -> tuple[cKDTree, np.ndarray, np.ndarray]:
    """
    Build a KDTree from a marine forecasting dataset for nearest neighbor search.
    The KDTree only includes coordinates where valid_var has non-NaN values.

    Args:
        ds: xarray Dataset containing latitude, longitude, and forecast variables
        valid_var: Name of the variable to use for filtering out NaN values
        time_slice: Dictionary of dimension name and initial value, which is
                    used as the slice to fildter out NaN values
                    (e.g., {"step": 0} or {"time": 0})

    Returns:
        tuple containing:
            - cKDTree: KDTree built from valid coordinates in radians
            - np.ndarray: Array of valid latitude values
            - np.ndarray: Array of valid longitude values
    """
    # create a mask from data where valid_var is null
    # and occurs at time_slice. invert to include only
    # valid data
    valid_mask = ~ds[valid_var].isel(**time_slice).isnull()

    lat_grid, lon_grid = np.meshgrid(ds.latitude, ds.longitude, indexing="ij")
    valid_lats = lat_grid[valid_mask.values]
    valid_lons = lon_grid[valid_mask.values]

    # convert to radians, build cKDTree w/ valid coords
    coords_rad = np.column_stack([np.radians(valid_lats), np.radians(valid_lons)])
    tree = cKDTree(coords_rad)

    return (tree, valid_lats, valid_lons)


def query_nearest_forecast_points(
    tree: cKDTree,
    valid_lats: np.ndarray,
    valid_lons: np.ndarray,
    target_lats: np.ndarray,
    target_lons: np.ndarray,
    max_distance_km: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Query the KDTree for nearest valid points to target coordinates.

    Helper function used in conjunction with build_forecast_kdtree. Runs the tree's
    query in a vectorized format to return all selected latitudes and longitudes
    from the target lat and lons provided.

    Args:
        tree: cKDTree built from valid forecast coordinates (in radians)
        valid_lats: Array of valid latitude values corresponding to tree nodes
        valid_lons: Array of valid longitude values corresponding to tree nodes
        target_lats: Array of target latitude values to query
        target_lons: Array of target longitude values to query
        max_distance_km: Optional maximum distance threshold in kilometers.
                        Points beyond this distance will have NaN lat/lon values.

    Returns:
        tuple containing:
            - np.ndarray: Selected latitude values for each target point
            - np.ndarray: Selected longitude values for each target point
            - np.ndarray: Distances in kilometers from each target to its nearest point
    """
    target_coords = np.column_stack([np.radians(target_lats), np.radians(target_lons)])

    # NOTE: cKDTree does use eucidlian distance therefore locations / regions
    # with high latitudes will see more distortion for nearest neighbor selections.
    # for the current envisioned usecase, this is not super nessicary.
    # IF working with grid resolutions > 5km at latitudes nearby +/-45, consider
    # switching to BallTree data-structure or using latitude weighted longitudes

    distances, indices = tree.query(target_coords)

    selected_lats = valid_lats[indices]
    selected_lons = valid_lons[indices]
    distances_km = np.atleast_1d(distances * EARTH_MEAN_RADIUS_KM)

    if max_distance_km is not None:
        out_of_bounds_mask = distances_km > max_distance_km
        selected_lats[out_of_bounds_mask] = np.nan
        selected_lons[out_of_bounds_mask] = np.nan

    return (selected_lats, selected_lons, distances_km)
