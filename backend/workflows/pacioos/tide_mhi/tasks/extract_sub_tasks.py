from pathlib import Path
import time

import numpy as np
import xarray as xr
from prefect import task, get_run_logger

from utils.geo_spatial import build_forecast_kdtree


@task(name="tide-open-netcdf", retries=3, retry_delay_seconds=10)
def open_netcdf(file_path: Path) -> xr.Dataset:
    """
    Open NetCDF dataset - blocking I/O operation.

    This operation typically takes 1-2 seconds.

    Args:
        file_path: Path to NetCDF file

    Returns:
        Opened xarray Dataset with tide forecast data
    """
    logger = get_run_logger()
    start_time = time.perf_counter()

    ds = xr.open_dataset(str(file_path))

    load_time = time.perf_counter() - start_time
    logger.info(
        "Opened NetCDF dataset",
        extra={
            "file": file_path.name,
            "data_vars": list(ds.data_vars.keys()),
            "dims": dict(ds.sizes),
            "load_time_seconds": round(load_time, 3),
        },
    )
    return ds


@task(name="tide-build-kdtree", retries=1)
def build_kdtree(ds: xr.Dataset, valid_var: str) -> tuple:
    """
    Build spatial index - CPU-bound operation.

    Creates a KDTree from valid ocean grid points for efficient nearest
    neighbor search.

    Args:
        ds: xarray Dataset containing forecast grid
        valid_var: Variable name to check for valid (non-NaN) values

    Returns:
        Tuple of (tree, valid_lats, valid_lons)
    """
    logger = get_run_logger()
    start_time = time.perf_counter()

    tree, valid_lats, valid_lons = build_forecast_kdtree(
        ds, valid_var=valid_var, time_slice={"time": 0}
    )

    kdtree_time = time.perf_counter() - start_time
    logger.info(
        "Built KDTree from forecast grid",
        extra={
            "grid_points": len(valid_lats),
            "build_time_seconds": round(kdtree_time, 3),
        },
    )
    return tree, valid_lats, valid_lons


@task(name="tide-select-spot-data", retries=1)
def select_spot_data(
    ds: xr.Dataset,
    selected_lats: np.ndarray,
    selected_lons: np.ndarray,
    spot_ids: np.ndarray,
    spot_lats: np.ndarray,
    spot_lons: np.ndarray,
    distances: np.ndarray,
) -> xr.Dataset:
    """
    Select forecast data for spots - CPU/memory bound operation.

    Uses xarray .sel() to extract time-series data for each spot from the
    full grid.

    Args:
        ds: Full forecast dataset
        selected_lats: Grid latitudes matched to spots
        selected_lons: Grid longitudes matched to spots
        spot_ids: Surf spot IDs
        spot_lats: Actual spot latitudes
        spot_lons: Actual spot longitudes
        distances: Distance from spot to nearest grid point (km)

    Returns:
        Dataset with forecast data for all spots
    """
    logger = get_run_logger()
    start_time = time.perf_counter()

    # Build spot-specific forecast dataset
    spot_forecast = (
        ds.sel(
            latitude=xr.DataArray(selected_lats, dims="spot"),
            longitude=xr.DataArray(selected_lons, dims="spot"),
        )
        .assign_coords(
            spot_id=("spot", spot_ids),
            spot_lat=("spot", spot_lats),
            spot_lon=("spot", spot_lons),
            distance_km=("spot", distances),
        )
        .rename(
            {
                "latitude": "selected_lat",
                "longitude": "selected_lon",
            }
        )
    )

    selection_time = time.perf_counter() - start_time
    logger.info(
        "Built spot forecast dataset",
        extra={
            "num_valid_spots": len(spot_ids),
            "selection_time_seconds": round(selection_time, 3),
        },
    )
    return spot_forecast
