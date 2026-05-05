from pathlib import Path

import numpy as np
import xarray as xr
from pandas import Timestamp
from prefect import task, get_run_logger

from services.forecast.pacioos_config import PacIOOSModelConfig
from workflows.pacioos.tide_mhi.tasks.extract_sub_tasks import open_netcdf
from workflows.utils import valid_ocean_lat_lon


@task(name="tide-mhi-extract-forecasts", retries=1)
def extract_forecasts(
    config: PacIOOSModelConfig,
    file_path: Path,
) -> list[dict]:
    """
    Extract raw forecast timeseries for all valid ocean grid cells.

    Returns a list of dicts — one per cell — each containing lat, lon,
    valid_times, and per-variable data arrays.
    """
    logger = get_run_logger()

    ds = open_netcdf(file_path)

    ssh_t0 = ds["ssh"].isel(time=0).values
    valid_lats, valid_lons = valid_ocean_lat_lon(ds, ssh_t0)

    total = ds["latitude"].size * ds["longitude"].size
    logger.info(
        f"Ocean cells: {len(valid_lats)}/{total} ({100 * len(valid_lats) / total:.1f}%)"
    )

    cell_ds = ds.sel(
        latitude=xr.DataArray(valid_lats, dims="cell"),
        longitude=xr.DataArray(valid_lons, dims="cell"),
    )

    valid_times = [Timestamp(vt) for vt in cell_ds.time.values]
    data_vars = [v for v in cell_ds.data_vars]
    arrs = {var: cell_ds[var].values for var in data_vars}

    raw_cells = [
        {
            "lat": float(valid_lats[i]),
            "lon": float(valid_lons[i]),
            "valid_times": valid_times,
            "data": {var: arrs[var][:, i] for var in data_vars},  # ndarray view
        }
        for i in range(len(valid_lats))
    ]

    ds.close()
    cell_ds.close()

    logger.info(
        f"Built raw {config.model_name.value} forecast dict for {len(raw_cells)} cells"
    )
    return raw_cells
