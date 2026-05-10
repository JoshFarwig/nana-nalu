from datetime import datetime, timedelta, timezone

from prefect import State, flow, get_run_logger
from prefect.states import Failed, Completed

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
    ingest_forecasts,
)
from workflows.nomads.nwps.tasks.download import cleanup_grib2_file
from workflows.nomads.nwps.tasks.sub_tasks import get_last_run_time


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
        logger.warning("Stale run, skipping execution")
        return Completed(
            message="Stale run, skipping", data={"status": "skipped", "reason": "stale"}
        )

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

    counts = {"success": 0, "already_current": 0, "no_data": 0, "error": 0}
    for r in results.values():
        status = r.get("status", "error")
        if status in counts:
            counts[status] += 1
        else:
            counts["error"] += 1

    logger.info(
        f"NWPS orchestration complete — "
        f"success={counts['success']} already_current={counts['already_current']} "
        f"no_data={counts['no_data']} error={counts['error']}",
        extra={
            "success": counts["success"],
            "already_current": counts["already_current"],
            "no_data": counts["no_data"],
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
    elif counts["no_data"] == len(regions):
        logger.warning("No data available from NOMADS for any region")
        return Completed(message="No data available from source", data=result_data)
    elif counts["success"] == 0:
        logger.info("All regions already current — nothing to process")
        return Completed(message="All regions already current", data=result_data)
    else:
        logger.info(
            f"Successfully processed {counts['success']}/{len(regions)} regions"
        )
        return Completed(
            message=f"Processed {counts['success']}/{len(regions)} regions",
            data=result_data,
        )


@flow(name="nwps-regional-processor")
def process_region_forecast(
    region: Region,
) -> dict:
    """
    Process NWPS forecast for a single region.

    Pipeline:
    1. Check last run time from DB (idempotency)
    2. Check NOMADS for latest available run
    3. Skip if already current or forecast too old
    4. Download GRIB2 file
    5. Ingest: extract → build rows → bulk insert
    6. Cleanup temp files

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

    last_run_time = get_last_run_time(
        config.provider_name, config.model_name.value, region.value
    )

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

    if last_run_time and last_run_time == run_datetime:
        logger.info(f"Already have last run {run_datetime.isoformat()}, skipping")
        return {"status": "already_current", "run": run_datetime.isoformat()}

    file_path = download_grib2(
        config=config,
        analysis_time=analysis_time,
        forecast_date=forecast_date,
    )

    rows_loaded = ingest_forecasts(
        config=config,
        file_path=file_path,
        provider=config.provider_name,
        model=config.model_name.value,
        region=region.value,
        run_time=run_datetime,
    )

    cleanup_grib2_file(file_path)

    logger.info(
        f"Successfully processed {region.value}",
        extra={"run_time": run_datetime.isoformat(), "rows": rows_loaded},
    )

    return {
        "status": "success",
        "region": region.value,
        "run": run_datetime.isoformat(),
        "rows_loaded": rows_loaded,
    }
