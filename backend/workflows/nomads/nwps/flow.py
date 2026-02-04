from datetime import datetime, timedelta, timezone

from prefect import State, flow, get_run_logger
from prefect.states import Cancelled, Failed, Completed

from services.forecast.nomads_config import (
    NOMADSModel,
    get_enabled_regions_for_model,
    get_nomads_config,
)
from utils.region import Region

from workflows.utils import stale_flow
from workflows.nomads.nwps.tasks import (
    check_availability,
    download_grib2,
    extract_forecasts,
    transform_forecasts,
    load,
)
from workflows.nomads.nwps.tasks.download import cleanup_grib2_file
from workflows.nomads.nwps.tasks.load import get_last_run_time


@flow(name="nwps-orchestration")
def orchestrate_nwps_forecasts() -> State[dict]:
    """
    Top-level orchestration flow for NWPS forecasts.

    Regions process sequentially. Each region and task fetches
    worker-scoped singleton resources as needed.

    Returns:
        State containing summary of processed regions and their results
    """
    logger = get_run_logger()

    if stale_flow(timedelta(hours=2)):
        logger.warning("Stale run, skipping exeuction")
        return Cancelled(message="Stale run, cancelling exeuction")

    logger.info("Starting NWPS orchestration")

    regions = get_enabled_regions_for_model(NOMADSModel.NWPS)

    if not regions:
        logger.warning("No enabled regions with NWPS configuration")
        return Completed(
            message="No enabled regions with NWPS configuration",
            data={"status": "no_regions", "regions_processed": 0},
        )

    logger.info(f"Processing {len(regions)} regions: {[r.value for r in regions]}")

    results = {}
    for region in regions:
        try:
            results[region.value] = process_region_forecast(region)
        except Exception as exc:
            logger.error(f"Region {region.value} failed with exception: {exc}")
            results[region.value] = {"status": "error", "error": str(exc)}

    successful = sum(1 for r in results.values() if r.get("status") == "success")
    logger.info(
        f"NWPS forecast orchestration complete: {successful}/{len(regions)} regions successful"
    )

    result_data = {
        "regions_processed": len(regions),
        "successful": successful,
        "results": results,
    }

    if successful == 0:
        logger.error(f"All regions failed: {list(results.keys())}")
        return Failed(message=f"All {len(regions)} regions failed", data=result_data)
    elif len(regions) > successful:
        failed_regions = [k for k, v in results.items() if v.get("status") != "success"]
        logger.warning(f"Partial failure, failed regions: {failed_regions}")
        return Completed(
            message=f"Partial completion, {successful}/{len(regions)} successful processed",
            data=result_data,
        )
    else:
        return Completed(
            message=f"Successfully processed all {len(regions)} regions",
            data=result_data,
        )


@flow(name="nwps-regional-processor")
def process_region_forecast(
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

    last_run_id = get_last_run_time(region.value)
    last_run_time = datetime.fromisoformat(last_run_id) if last_run_id else None

    latest_run = check_availability(
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

    file_path = download_grib2(
        config=config,
        analysis_time=analysis_time,
        forecast_date=forecast_date,
    )

    raw_forecasts = extract_forecasts(
        config=config,
        file_path=file_path,
    )

    transformed_forecasts = transform_forecasts(
        raw_forecasts=raw_forecasts,
        config=config,
    )

    spots_loaded = load(
        forecasts=transformed_forecasts,
        region=region.value,
        run_id=run_id,
    )

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
