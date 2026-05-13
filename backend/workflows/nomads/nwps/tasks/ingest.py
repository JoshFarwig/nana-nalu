"""
NWPS fused ingest task: extract → row build → DB insert in one task.

Streams cells in chunks to bound peak memory. No Pydantic in write path
(see workflows/nomads/nwps/mapper.py:build_nwps_rows). Single transaction
across all chunks for atomicity — rollback on any chunk failure.
"""

from datetime import datetime
from pathlib import Path
import time
from typing import cast

import numpy as np
import xarray as xr
from pandas import Timestamp, isna
from prefect import task, get_run_logger
from sqlalchemy import insert

from models.forecast_data import forecast_data
from models.model_run import ModelRun
from services.forecast.nomads_config import NWPSConfig
from workflows.nomads.nwps.mapper import build_nwps_rows
from workflows.nomads.nwps.tasks.sub_tasks import open_grib
from workflows.resources import get_resources
from workflows.utils import valid_ocean_lat_lon


CHUNK_CELLS = 500  # ~500 cells × 144 steps × ~500B = ~36MB per chunk


@task(name="nwps-ingest", retries=2, retry_delay_seconds=10, persist_result=False)
def ingest_forecasts(
    config: NWPSConfig,
    file_path: Path,
    provider: str,
    model: str,
    region: str,
    run_time: datetime,
) -> int:
    """
    Open GRIB2, stream chunks of cells through row builder + bulk insert.

    Single DB transaction wraps model_run insert + all forecast_data chunks.
    Failure anywhere rolls everything back, no partial runs.
    """

    logger = get_run_logger()
    resources = get_resources()
    t_start = time.perf_counter()

    # mask out land cells, choose slice + var where NaN ALWAYS = land, i.e. swell ("swh")
    ds = open_grib(file_path)
    valid_lats, valid_lons = valid_ocean_lat_lon(ds, mask_var="swh")

    n_cells = len(valid_lats)
    total_cells = ds["latitude"].size * ds["longitude"].size
    logger.info(
        f"Ocean cells: {n_cells}/{total_cells} ({100 * n_cells / total_cells:.1f}%)"
    )

    # calculate lat, lon resolutions and orgins for model run
    lat_vals = ds["latitude"].values
    lon_vals = ds["longitude"].values
    lat_origin = float(lat_vals[0])
    lon_origin = float(lon_vals[0])
    lat_res = float(lat_vals[1] - lat_vals[0])
    lon_res = float(lon_vals[1] - lon_vals[0])
    lat_count = len(lat_vals)
    lon_count = len(lon_vals)

    # vectorized pointwise select across all ocean cells (lazy until .values below)
    cell_ds = ds.sel(
        latitude=xr.DataArray(valid_lats, dims="cell"),
        longitude=xr.DataArray(valid_lons, dims="cell"),
    ).swap_dims({"step": "valid_time"})

    valid_times = cast(
        list[Timestamp],
        [Timestamp(vt) for vt in cell_ds.valid_time.values if not isna(vt)],
    )
    arrs_full: dict[str, np.ndarray] = {
        str(var): cell_ds[var].values for var in cell_ds.data_vars
    }

    horizon_start = min(valid_times)
    horizon_end = min(valid_times)

    ds.close()
    cell_ds.close()

    rows_loaded = 0
    with resources.db.auto_commit_session() as session:
        run = ModelRun(
            provider=provider,
            model=model,
            region=region,
            lat_origin=lat_origin,
            lon_origin=lon_origin,
            lat_res=lat_res,
            lon_res=lon_res,
            lat_count=lat_count,
            lon_count=lon_count,
            run_time=run_time,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
        )
        session.add(run)
        session.flush()
        model_run_id = run.id

        log_every = max(1, (n_cells + CHUNK_CELLS - 1) // CHUNK_CELLS // 10)

        for chunk_start in range(0, n_cells, CHUNK_CELLS):
            chunk_end = min(chunk_start + CHUNK_CELLS, n_cells)
            chunk_lats = valid_lats[chunk_start:chunk_end]
            chunk_lons = valid_lons[chunk_start:chunk_end]
            chunk_arrs = {
                var: arr[:, chunk_start:chunk_end] for var, arr in arrs_full.items()
            }

            rows = build_nwps_rows(
                lats=chunk_lats,
                lons=chunk_lons,
                valid_times=valid_times,
                arrs=chunk_arrs,
                model_run_id=model_run_id,
            )
            session.execute(insert(forecast_data), rows)
            rows_loaded += len(rows)
            if (chunk_start // CHUNK_CELLS) % log_every == 0:
                logger.info(
                    f"Inserted chunk {chunk_start // CHUNK_CELLS + 1}"
                    f"/{(n_cells + CHUNK_CELLS - 1) // CHUNK_CELLS} "
                    f"({rows_loaded} rows so far)"
                )

    elapsed = time.perf_counter() - t_start
    logger.info(
        f"Ingest complete: {rows_loaded} rows, {n_cells} cells, {elapsed:.1f}s",
        extra={
            "provider": provider,
            "model": model,
            "region": region,
            "run_time": run_time.isoformat(),
            "rows": rows_loaded,
            "cells": n_cells,
            "elapsed_seconds": round(elapsed, 2),
        },
    )
    return rows_loaded
