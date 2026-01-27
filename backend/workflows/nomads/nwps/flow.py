"""
NOMADS NWPS orchestration flows.

Top-level flow initializes resources and dispatches to regional processors.
Regional flow coordinates the ETL pipeline: availability → download → extract → transform → load.
"""

from datetime import datetime, timezone

from prefect import flow, get_run_logger

from workflows.resources import ForecastResources, forecast_resources
from services.forecast.nomads_config import (
    NOMADSModel,
    NWPSConfig,
    get_enabled_regions_for_model,
    get_nomads_config,
)
from utils.region import Region

from .tasks import check_availability, download_grib2, extract_forecasts, transform_forecasts, load
from .tasks.download import cleanup_grib2_file
from .tasks.load import get_last_run_time


@flow(name="nwps-orchestration")
async def orchestrate_nwps_forecasts() -> dict:
    """
    Top-level orchestration flow for NWPS forecasts.

    Initializes shared resources once, then processes each enabled region.
    Resources are shared across all subflow calls (same process).

    Returns:
        Summary of processed regions and their results
    """
    logger = get_run_logger()

    async with forecast_resources() as resources:
        logger.info("Starting NWPS orchestration")

        regions = get_enabled_regions_for_model(NOMADSModel.NWPS)

        if not regions:
            logger.warning("No enabled regions with NWPS configuration")
            return {"status": "no_regions", "regions_processed": 0}

        logger.info(f"Processing {len(regions)} regions: {[r.value for r in regions]}")

        results = {}
        for region in regions:
            result = await process_region_forecast(region, resources)
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
    resources: ForecastResources,
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
        resources: Shared resource managers

    Returns:
        Processing result with status and metadata
    """
    logger = get_run_logger()
    config = get_nomads_config(region, NOMADSModel.NWPS)

    logger.info(
        f"Processing {region.value}",
        extra={"wfo": config.wfo.value, "cg": config.cg},
    )

    # TODO(human): Implement the retry decision logic
    # See "Learn by Doing" section below for guidance

    # Get last run time for idempotency check
    last_run_id = await get_last_run_time(resources.redis.client, region.value)
    last_run_time = datetime.fromisoformat(last_run_id) if last_run_id else None

    # Check availability
    latest_run = await check_availability(
        config=config,
        http=resources.http,
        last_run_time=last_run_time,
    )

    if not latest_run:
        logger.info(f"No new run available for {region.value}")
        return {"status": "no_data", "region": region.value}

    forecast_date, analysis_time = latest_run
    run_datetime = datetime.combine(forecast_date, analysis_time, tzinfo=timezone.utc)
    run_id = run_datetime.isoformat()

    # Idempotency check
    if last_run_id == run_id:
        logger.info(f"Already have latest run {run_id}, skipping")
        return {"status": "already_current", "run": run_id}

    # Age check
    age_hours = (datetime.now(timezone.utc) - run_datetime).total_seconds() / 3600
    if age_hours > config.max_forecast_age_hours:
        logger.warning(
            f"Run {run_id} is {age_hours:.1f}h old (max: {config.max_forecast_age_hours}h)"
        )
        return {"status": "too_old", "run": run_id, "age_hours": age_hours}

    # Download
    file_path = await download_grib2(
        config=config,
        http=resources.http,
        analysis_time=analysis_time,
        forecast_date=forecast_date,
    )

    # Extract raw forecasts (needs database session)
    async with resources.db.explicit_commit_session() as session:
        raw_forecasts = await extract_forecasts(
            config=config,
            file_path=file_path,
            session=session,
        )

    # Transform to unified schema
    transformed_forecasts = transform_forecasts(
        raw_forecasts=raw_forecasts,
        config=config,
    )

    # Load to Redis
    spots_loaded = await load(
        forecasts=transformed_forecasts,
        redis_client=resources.redis.client,
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
