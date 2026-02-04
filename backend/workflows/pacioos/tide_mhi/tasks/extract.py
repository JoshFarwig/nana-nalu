"""
Extract forecast data from PacIOOS NetCDF files.

Uses xarray to read NetCDF files (native format, no special engine needed).
Builds KDTree for nearest-neighbor matching of surf spots to grid points.
"""

from pathlib import Path
import time

import numpy as np
from pandas import Timestamp
from prefect import task, get_run_logger

from repositories.surf_spot_repository import SyncSurfSpotRepository
from services.forecast.pacioos_config import PacIOOSModelConfig
from utils.geo_spatial import query_nearest_forecast_points
from workflows.resources import get_resources
from workflows.pacioos.tide_mhi.tasks.extract_sub_tasks import (
    open_netcdf,
    build_kdtree,
    select_spot_data,
)


@task(name="tide-mhi-extract-forecasts", retries=1)
def extract_forecasts(
    config: PacIOOSModelConfig,
    file_path: Path,
) -> dict[int, dict]:
    """
    Extract raw forecasts for all surf spots within the PacIOOS grid.

    Process:
    1. Query surf spots within grid bounding box
    2. Open NetCDF file with xarray
    3. Build KDTree of valid ocean grid points
    4. Nearest-neighbor search to match spots to grid cells
    5. Extract time-series data for each matched spot

    Args:
        config: PacIOOS model configuration
        file_path: Path to downloaded NetCDF file

    Returns:
        Dictionary mapping spot_id -> raw forecast data
    """
    resources = get_resources()
    logger = get_run_logger()

    with resources.db.explicit_commit_session() as session:
        repo = SyncSurfSpotRepository(session)

        # Get spots within grid bounds
        spots = repo.get_all_in_grid(
            config.grid.lat_min,
            config.grid.lat_max,
            config.grid.long_min,
            config.grid.long_max,
            is_active=True,
        )

    if not spots:
        logger.warning(f"No active spots found in grid for {config.region.value}")
        return {}

    logger.info(f"Found {len(spots)} spots in grid bounds")

    ds = open_netcdf(file_path)

    # Prepare spot coordinates as numpy arrays
    spot_ids = np.array([spot["id"] for spot in spots])
    spot_lats = np.array([spot["latitude"] for spot in spots])
    spot_lons = np.array([spot["longitude"] for spot in spots])

    tree, valid_lats, valid_lons = build_kdtree(ds, config.data_variables[0])

    # NN search (fast, vectorized)
    start_time = time.perf_counter()
    selected_lats, selected_lons, distances = query_nearest_forecast_points(
        tree,
        valid_lats,
        valid_lons,
        spot_lats,
        spot_lons,
        max_distance_km=config.max_nearest_neighbor_distance_km,
    )
    nn_search_time = time.perf_counter() - start_time

    logger.info(
        "Completed nearest neighbor search",
        extra={
            "num_spots": len(spot_ids),
            "search_time_seconds": round(nn_search_time, 3),
        },
    )

    # Filter spots outside max distance threshold
    valid_mask = ~np.isnan(selected_lats)

    if not valid_mask.all():
        filtered_count = (~valid_mask).sum()
        logger.warning(
            f"{filtered_count} spots filtered - exceed {config.max_nearest_neighbor_distance_km}km threshold"
        )

    # Extract valid spots
    valid_spot_ids = spot_ids[valid_mask]
    valid_selected_lats = selected_lats[valid_mask]
    valid_selected_lons = selected_lons[valid_mask]
    valid_distances = distances[valid_mask]

    spot_forecast = select_spot_data(
        ds,
        valid_selected_lats,
        valid_selected_lons,
        valid_spot_ids,
        spot_lats[valid_mask],
        spot_lons[valid_mask],
        valid_distances,
    )

    # Dictionary building (fast)
    start_time = time.perf_counter()
    raw_forecasts = _build_forecast_dict(
        spot_forecast,
        valid_spot_ids,
        valid_selected_lats,
        valid_selected_lons,
        valid_distances,
    )
    dict_build_time = time.perf_counter() - start_time

    logger.info(
        "Built forecast dictionary",
        extra={"dict_build_time_seconds": round(dict_build_time, 3)},
    )

    # Close datasets
    ds.close()
    spot_forecast.close()

    logger.info(
        f"Extracted raw forecasts for {len(raw_forecasts)} spots",
        extra={"spot_ids": list(raw_forecasts.keys())},
    )

    return raw_forecasts


def _build_forecast_dict(
    spot_forecast,
    spot_ids: np.ndarray,
    selected_lats: np.ndarray,
    selected_lons: np.ndarray,
    distances: np.ndarray,
) -> dict:
    """Build forecast dictionary from xarray Dataset."""
    forecasts = {}

    # Extract time coordinates
    valid_times = [Timestamp(vt) for vt in spot_forecast.time.values]

    # Get data variable names (exclude coordinate variables)
    data_vars = [var for var in spot_forecast.data_vars if var not in ["time"]]

    # Vectorized extraction - transpose to (num_spots, num_timesteps)
    data_arrays = {var: spot_forecast[var].values.T for var in data_vars}

    # Build dictionary for each spot
    for i, spot_id in enumerate(spot_ids):
        forecasts[int(spot_id)] = {
            "spot_id": int(spot_id),
            "grid_metadata": {
                "selected_lat": float(selected_lats[i]),
                "selected_lon": float(selected_lons[i]),
                "distance_km": float(distances[i]),
            },
            "valid_times": valid_times,
            "data": {var: data_arrays[var][i].tolist() for var in data_vars},
        }

    return forecasts
