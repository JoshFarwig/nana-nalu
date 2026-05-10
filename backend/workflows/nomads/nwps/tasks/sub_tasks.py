"""
Sub-tasks for NWPS forecast pipeline.

Helpers called from the parent ingest/orchestration tasks: GRIB2 open
and last-run lookup for idempotency.
"""

from datetime import datetime
from pathlib import Path
import time

import xarray as xr
from prefect import task, get_run_logger
from sqlalchemy import select

from models.model_run import ModelRun
from workflows.resources import get_resources


@task(name="nwps-open-grib", retries=3, retry_delay_seconds=10)
def open_grib(file_path: Path) -> xr.Dataset:
    """
    Open GRIB2 dataset - blocking I/O operation.

    Most time-consuming step in extraction, typically 2-3 seconds.
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


def get_last_run_time(provider: str, model: str, region: str) -> datetime | None:
    """Most recent run_time loaded for this provider/model/region, or None."""
    resources = get_resources()
    with resources.db.explicit_commit_session() as session:
        result = session.execute(
            select(ModelRun.run_time)
            .where(
                ModelRun.provider == provider,
                ModelRun.model == model,
                ModelRun.region == region,
            )
            .order_by(ModelRun.run_time.desc())
            .limit(1)
        ).scalar_one_or_none()
    return result
