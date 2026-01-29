"""
Sub-tasks for NWPS forecast extraction.

These tasks are designed to run in a ThreadPoolTaskRunner to enable true
concurrent execution across multiple regions. Each task wraps a blocking
operation (I/O or CPU-bound) that would otherwise block the async event loop.
"""

from pathlib import Path
import time

import numpy as np
import xarray as xr
from prefect import task, get_run_logger

from utils.geo_spatial import build_forecast_kdtree


@task(name="nwps-open-grib", retries=3, retry_delay_seconds=10)
def open_grib(file_path: Path) -> xr.Dataset:
    """
    Open GRIB2 dataset - blocking I/O operation.

    This is the most time-consuming operation in the extraction pipeline,
    typically taking 2-3 seconds. Running in a thread pool allows multiple
    regions to load their GRIB files concurrently.

    Args:
        file_path: Path to GRIB2 file

    Returns:
        Opened xarray Dataset with forecast data
    """
    logger = get_run_logger()
    start_time = time.perf_counter()

    ds = xr.open_dataset(
        str(file_path),
        engine="cfgrib",
        filter_by_keys={"dataType": "fc"},
    )

    load_time = time.perf_counter() - start_time
    logger.info(
        "Opened GRIB2 dataset",
        extra={
            "file": file_path.name,
            "data_vars": list(ds.data_vars.keys()),
            "load_time_seconds": round(load_time, 3),
        },
    )
    return ds


@task(name="nwps-build-kdtree", retries=1)
def build_kdtree(ds: xr.Dataset) -> tuple:
    """
    Build spatial index - CPU-bound operation.

    Creates a KDTree from valid ocean grid points for efficient nearest
    neighbor search. Takes ~0.2 seconds but blocks the event loop.

    Args:
        ds: xarray Dataset containing forecast grid

    Returns:
        Tuple of (tree, valid_lats, valid_lons)
    """
    logger = get_run_logger()
    start_time = time.perf_counter()

    tree, valid_lats, valid_lons = build_forecast_kdtree(
        ds, valid_var="swh", time_slice={"step": 0}
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


@task(name="nwps-select-spot-data", retries=1)
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
    full grid. Can take 1-2 seconds for large grids or many spots.

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
                "time": "analysis_time",
            }
        )
        .swap_dims({"step": "valid_time"})
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
