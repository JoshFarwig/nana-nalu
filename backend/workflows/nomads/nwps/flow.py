import asyncio
from datetime import datetime, timezone

from prefect import flow, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner

from services.forecast.nomads_config import (
    NOMADSModel,
    get_enabled_regions_for_model,
    get_nomads_config,
)
from utils.region import Region

from workflows.nomads.nwps.tasks import (
    check_availability,
    download_grib2,
    extract_forecasts,
    transform_forecasts,
    load,
)
from workflows.nomads.nwps.tasks.download import cleanup_grib2_file
from workflows.nomads.nwps.tasks.load import get_last_run_time


@flow(name="nwps-orchestration", task_runner=ThreadPoolTaskRunner(max_workers=4))  # type: ignore[arg-type]
async def orchestrate_nwps_forecasts() -> dict:
    """
    Top-level orchestration flow for NWPS forecasts.

    All regions process in concurrently using asyncio.gather. Each region
    and task fetches worker-scoped singleton resources as needed.

    Returns:
        Summary of processed regions and their results
    """
    logger = get_run_logger()

    logger.info("Starting NWPS orchestration")

    regions = get_enabled_regions_for_model(NOMADSModel.NWPS)

    if not regions:
        logger.warning("No enabled regions with NWPS configuration")
        return {"status": "no_regions", "regions_processed": 0}

    logger.info(f"Processing {len(regions)} regions: {[r.value for r in regions]}")

    region_tasks = [process_region_forecast(region) for region in regions]
    results_list = await asyncio.gather(*region_tasks, return_exceptions=True)

    results = {}
    for region, result in zip(regions, results_list):
        if isinstance(result, Exception):
            logger.error(f"Region {region.value} failed with exception: {result}")
            results[region.value] = {"status": "error", "error": str(result)}
        else:
            results[region.value] = result

    successful = sum(1 for r in results.values() if r.get("status") == "success")
    logger.info(
        f"NWPS forecast orchestration complete: {successful}/{len(regions)} regions successful"
    )

    return {
        "status": "complete",
        "regions_processed": len(regions),
        "successful": successful,
        "results": results,
    }


@flow(name="nwps-regional-processor")
async def process_region_forecast(
    region: Region,
) -> dict:
    """
    Process NWPS forecast for a single region.

    Pipeline:
    1. Check last run time from Redis (idempotency)
    2. Check NOMADS for latest available run
    3. Skip if already current or forecast too old
    4. Download GRIB2 file (Extract)
    5. Extract raw forecasts for surf spots
    6. Transform raw data to unified schema
    7. Load forecasts to Redis with TTL
    8. Cleanup temp files

    Args:
        region: Geographic region to process

    Returns:
        Processing result with status and metadata
    """
    logger = get_run_logger()
    config = get_nomads_config(region, NOMADSModel.NWPS)

    logger.info(
        f"Processing {region.value}",
        extra={"wfo": config.wfo.value, "cg": config.cg},
    )

    last_run_id = await get_last_run_time(region.value)
    last_run_time = datetime.fromisoformat(last_run_id) if last_run_id else None

    latest_run = await check_availability(
        config=config,
        last_run_time=last_run_time,
        max_lookback_hours=config.max_forecast_age_hours,
    )

    if not latest_run:
        logger.info(f"No run available for {region.value}")
        return {"status": "no_data", "region": region.value}

    forecast_date, analysis_time = latest_run
    run_datetime = datetime.combine(forecast_date, analysis_time, tzinfo=timezone.utc)
    run_id = run_datetime.isoformat()

    if last_run_id == run_id:
        logger.info(f"Already have last run {run_id}, skipping")
        return {"status": "already_current", "run": run_id}

    # Download
    file_path = await download_grib2(
        config=config,
        analysis_time=analysis_time,
        forecast_date=forecast_date,
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
    cleanup_grib2_file(file_path)

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
