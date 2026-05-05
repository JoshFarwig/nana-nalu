"""
Sub-tasks for NWPS forecast extraction.

Each task wraps a blocking operation (I/O or CPU-bound) that is called
directly from the parent extract task.
"""

from pathlib import Path
import time

import xarray as xr
from prefect import task, get_run_logger


@task(name="nwps-open-grib", retries=3, retry_delay_seconds=10)
def open_grib(file_path: Path) -> xr.Dataset:
    """
    Open GRIB2 dataset - blocking I/O operation.

    This is the most time-consuming operation in the extraction pipeline,
    typically taking 2-3 seconds.

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
        # retrieve forcast dataset. fc=forecast dataset, an=analysis dataset
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
