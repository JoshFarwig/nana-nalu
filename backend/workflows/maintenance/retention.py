"""
Retention flow: deletes model_runs older than 14 days (by created_at).
forecast_data rows are removed automatically via ON DELETE CASCADE.

Schedule: daily at 03:00 UTC via Prefect deployment cron "0 3 * * *"
"""

from datetime import datetime, timedelta, timezone

from prefect import State, flow, get_run_logger, task
from prefect.states import Completed, Failed
from sqlalchemy import delete

from models.model_run import ModelRun
from workflows.resources import get_resources
from workflows.utils import stale_flow


@task(name="retention-delete-stale-runs", retries=1, retry_delay_seconds=30)
def delete_stale_runs(cutoff: datetime) -> int:
    """Delete model_runs older than cutoff. forecast_data cascades automatically."""
    logger = get_run_logger()
    resources = get_resources()

    with resources.db.auto_commit_session() as session:
        result = session.execute(delete(ModelRun).where(ModelRun.created_at < cutoff))

    deleted = result.rowcount
    logger.info(
        "Retention delete complete",
        extra={"cutoff": cutoff.isoformat(), "model_runs_deleted": deleted},
    )
    return deleted


@flow(name="forecast-retention")
def run_retention() -> State[dict]:
    """
    Daily retention flow. Deletes model_runs (+ forecast_data via cascade)
    with created_at older than 14 days.

    Deploy with cron: "0 3 * * *" (03:00 UTC daily)
    """
    logger = get_run_logger()

    if stale_flow(timedelta(hours=6)):
        logger.warning("Stale run, skipping execution")
        return Completed(
            message="Stale run, skipping",
            data={"status": "skipped", "reason": "stale"},
        )

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=14)
    logger.info("Starting retention", extra={"cutoff": cutoff.isoformat()})

    try:
        deleted = delete_stale_runs(cutoff)
    except Exception as exc:
        logger.error(f"Retention failed: {exc}")
        return Failed(message=f"Retention failed: {exc}")

    return Completed(
        message=f"Deleted {deleted} stale model runs",
        data={"model_runs_deleted": deleted},
    )
