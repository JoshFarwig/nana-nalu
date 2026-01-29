"""
PacIOOS Tide MHI orchestration flows.

Top-level flow initializes resources and dispatches to regional processors.
Regional flow coordinates the ETL pipeline: download → extract → transform → load.

Note: Unlike NOMADS operational forecasts, PacIOOS tide data is pre-computed
harmonic analysis extending through December 2026. No availability check needed.
"""

import asyncio
from datetime import datetime, timezone, timedelta

from prefect import flow, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner

from workflows.resources import get_resources
from services.forecast.pacioos_config import (
    PacIOOSModel,
    get_enabled_regions_for_model,
    get_pacioos_config,
)
from utils.region import Region

from .tasks import download_netcdf, extract_forecasts, transform_forecasts, load
from .tasks.download import cleanup_netcdf_file
from .tasks.load import get_last_run_time


@flow(
    name="tide-mhi-orchestration",
    task_runner=ThreadPoolTaskRunner(max_workers=8),  # type: ignore[arg-type]
)
async def orchestrate_tide_forecasts() -> dict:
    """
    Top-level orchestration flow for PacIOOS Tide MHI forecasts.

    All regions process in parallel using asyncio.gather. Each region
    and task fetches worker-scoped singleton resources as needed.

    Returns:
        Summary of processed regions and their results
    """
    logger = get_run_logger()

    logger.info("Starting PacIOOS Tide MHI orchestration")

    regions = get_enabled_regions_for_model(PacIOOSModel.TIDE)

    if not regions:
        logger.warning("No enabled regions with Tide configuration")
        return {"status": "no_regions", "regions_processed": 0}

    logger.info(f"Processing {len(regions)} regions: {[r.value for r in regions]}")

    # Process all regions concurrently
    region_tasks = [process_region_forecast(region) for region in regions]
    results_list = await asyncio.gather(*region_tasks, return_exceptions=True)

    # Build results dict and handle exceptions
    results = {}
    for region, result in zip(regions, results_list):
        if isinstance(result, Exception):
            logger.error(f"Region {region.value} failed with exception: {result}")
            results[region.value] = {"status": "error", "error": str(result)}
        else:
            results[region.value] = result

    successful = sum(1 for r in results.values() if r.get("status") == "success")
    logger.info(
        f"Tide forecast orchestration complete: {successful}/{len(regions)} regions successful"
    )

    return {
        "status": "complete",
        "regions_processed": len(regions),
        "successful": successful,
        "results": results,
    }


@flow(name="tide-mhi-regional-processor")
async def process_region_forecast(
    region: Region,
) -> dict:
    """
    Process PacIOOS Tide forecast for a single region.

    Pipeline:
    1. Check last run time from Redis (idempotency)
    2. Skip if refresh not due (weekly refresh cycle)
    3. Download NetCDF via GridDAP (Extract)
    4. Extract raw forecasts for surf spots
    5. Transform raw data to unified schema
    6. Load forecasts to Redis with TTL
    7. Cleanup temp files

    Unlike NOMADS, no availability check needed - tide data is pre-computed
    and always available from ERDDAP.

    Args:
        region: Geographic region to process

    Returns:
        Processing result with status and metadata
    """
    logger = get_run_logger()
    resources = await get_resources()
    config = get_pacioos_config(region, PacIOOSModel.TIDE)

    logger.info(
        f"Processing {region.value}",
        extra={"model": config.model_name.value, "dataset": config.dataset_id},
    )

    # Get last run time for refresh interval check
    last_run_id = await get_last_run_time(region.value)
    last_run_time = datetime.fromisoformat(last_run_id) if last_run_id else None

    # Check if refresh is due (weekly cycle for tide predictions)
    now = datetime.now(timezone.utc)

    if last_run_time:
        hours_since_last_run = (now - last_run_time).total_seconds() / 3600
        if hours_since_last_run < config.max_forecast_age_hours:
            logger.info(
                f"Skipping {region.value} - last refresh was {hours_since_last_run:.1f}h ago "
                f"(threshold: {config.max_forecast_age_hours}h)"
            )
            return {
                "status": "skip_not_due",
                "region": region.value,
                "last_run": last_run_id,
                "hours_since": round(hours_since_last_run, 1),
            }

    # Generate run ID (download timestamp since no model analysis time for pre-computed data)
    run_id = now.isoformat()

    # Download
    file_path = await download_netcdf(
        config=config,
    )

    # Extract raw forecasts
    raw_forecasts = await extract_forecasts(
        config=config,
        file_path=file_path,
    )

    # Transform to unified schema
    transformed_forecasts = transform_forecasts(
        raw_forecasts=raw_forecasts,
        config=config,
    )

    # Load to Redis
    spots_loaded = await load(
        forecasts=transformed_forecasts,
        region=region.value,
        run_id=run_id,
    )

    # Cleanup
    cleanup_netcdf_file(file_path)

    logger.info(
        f"Successfully processed {region.value}",
        extra={"run_id": run_id, "spots": spots_loaded},
    )

    return {
        "status": "success",
        "region": region.value,
        "run": run_id,
        "spots_processed": spots_loaded,
    }
