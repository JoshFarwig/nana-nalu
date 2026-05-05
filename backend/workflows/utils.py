import numpy as np
from datetime import datetime, timedelta, timezone
from prefect.runtime.flow_run import get_scheduled_start_time
from xarray import Dataset


def stale_flow(fresh_threshold: timedelta) -> bool:
    scheduled_start_time = get_scheduled_start_time()
    if scheduled_start_time is None:
        return False

    now = datetime.now(tz=timezone.utc)
    difference = now - scheduled_start_time

    return difference > fresh_threshold


def valid_ocean_lat_lon(
    ds: Dataset,
    t0_slice: np.ndarray,
    lat_dim: str = "latitude",
    lon_dim: str = "longitude",
) -> tuple[np.ndarray, np.ndarray]:
    ocean_mask = ~np.isnan(t0_slice)
    lat2d, lon2d = np.meshgrid(ds[lat_dim].values, ds[lon_dim].values, indexing="ij")
    valid_lats = lat2d[ocean_mask]
    valid_lons = lon2d[ocean_mask]

    return valid_lats, valid_lons
