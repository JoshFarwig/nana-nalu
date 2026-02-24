from datetime import datetime, timezone, timedelta

from prefect import State, flow, get_run_logger
from prefect.states import Cancelled, Completed, Failed

from workflows.resources import get_resources
from workflows.utils import stale_flow
from services.forecast.pacioos_config import (
    PacIOOSModel,
    get_enabled_regions_for_model,
    get_pacioos_config,
)
from utils.region import Region

from .tasks import download_netcdf, extract_forecasts, transform_forecasts, load
from .tasks.download import cleanup_netcdf_file
from .tasks.load import get_last_run_time


@flow(name="tide-mhi-orchestration")
def orchestrate_tide_forecasts() -> State[dict]:
    """
    Top-level orchestration flow for PacIOOS Tide MHI forecasts.

    Regions process sequentially. Each region and task fetches
    worker-scoped singleton resources as needed.

    Returns:
        State containing summary of processed regions and their results
    """
    logger = get_run_logger()

    if stale_flow(timedelta(hours=2)):
        logger.warning("Stale run, skipping execution")
        return Cancelled(message="Stale run, cancelling execution")

    logger.info("Starting PacIOOS Tide MHI orchestration")

    regions = get_enabled_regions_for_model(PacIOOSModel.TIDE_MHI)

    if not regions:
        logger.warning("No enabled regions with Tide configuration")
        return Completed(
            message="No enabled regions with Tide configuration",
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

    counts = {"success": 0, "skip_not_due": 0, "error": 0}
    for r in results.values():
        status = r.get("status", "error")
        if status in counts:
            counts[status] += 1
        else:
            counts["error"] += 1

    logger.info(
        f"Tide MHI orchestration complete — "
        f"success={counts['success']} skip_not_due={counts['skip_not_due']} error={counts['error']}",
        extra={
            "success": counts["success"],
            "skip_not_due": counts["skip_not_due"],
            "error": counts["error"],
        },
    )

    result_data = {
        "regions_processed": len(regions),
        "counts": counts,
        "results": results,
    }

    errored = [k for k, v in results.items() if v.get("status") == "error"]

    if counts["error"] == len(regions):
        logger.error(f"All regions errored: {errored}")
        return Failed(message=f"All {len(regions)} regions errored: {errored}")
    elif counts["error"] > 0:
        logger.warning(f"Partial failure — errored regions: {errored}")
        return Completed(
            message=f"Partial failure: {counts['success']} success, {counts['error']} errored",
            data=result_data,
        )
    elif counts["success"] == 0:
        logger.info("All regions skipped — refresh not yet due")
        return Completed(
            message="All regions skipped, refresh not yet due", data=result_data
        )
    else:
        logger.info(
            f"Successfully processed {counts['success']}/{len(regions)} regions"
        )
        return Completed(
            message=f"Processed {counts['success']}/{len(regions)} regions",
            data=result_data,
        )


@flow(name="tide-mhi-regional-processor")
def process_region_forecast(
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
    resources = get_resources()
    config = get_pacioos_config(region, PacIOOSModel.TIDE_MHI)

    logger.info(
        f"Processing {region.value}",
        extra={"model": config.model_name.value, "dataset": config.dataset_id},
    )

    # Get last run time for refresh interval check
    last_run_id = get_last_run_time(config.provider_name, config.model_name.value, region.value)
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
    file_path = download_netcdf(
        config=config,
    )

    # Extract raw forecasts
    raw_forecasts = extract_forecasts(
        config=config,
        file_path=file_path,
    )

    # Transform to unified schema
    transformed_forecasts = transform_forecasts(
        raw_forecasts=raw_forecasts,
        config=config,
    )

    # Load to Redis
    spots_loaded = load(
        forecasts=transformed_forecasts,
        provider=config.provider_name,
        model=config.model_name.value,
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
