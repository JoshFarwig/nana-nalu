from pathlib import Path
import time

import numpy as np
import xarray as xr
from prefect import task, get_run_logger


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
