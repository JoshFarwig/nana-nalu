from datetime import datetime

from prefect import task, get_run_logger
from sqlalchemy import insert, select, text

from models.forecast_data import forecast_data
from models.model_run import ModelRun
from services.forecast.forecast_schema import GridCellForecast
from workflows.resources import get_resources


@task(name="nwps-load", retries=2, retry_delay_seconds=10)
def load(
    cells: list[GridCellForecast],
    provider: str,
    model: str,
    region: str,
    run_time: datetime,
) -> int:
    """
    Load grid cell forecasts into TimescaleDB.

    Inserts a model_run row for idempotency, then bulk-inserts all
    grid cell timeseries rows into forecast_data.

    Returns number of rows inserted.
    """
    logger = get_run_logger()
    resources = get_resources()

    if not cells:
        logger.warning("No cells to load")
        return 0

    with resources.db.auto_commit_session() as session:
        run = ModelRun(
            provider=provider,
            model=model,
            region=region,
            run_time=run_time,
        )
        session.add(run)
        session.flush()
        model_run_id = run.id

        rows = []
        for cell in cells:
            rows.extend(cell.to_db_rows(model_run_id))

        session.execute(insert(forecast_data), rows)

    logger.info(
        f"Loaded {len(rows)} rows for {len(cells)} cells",
        extra={
            "provider": provider,
            "model": model,
            "region": region,
            "run_time": run_time.isoformat(),
        },
    )
    return len(rows)


def get_last_run_time(provider: str, model: str, region: str) -> datetime | None:
    """
    Query model_runs for the most recent successful run_time for this provider/model/region.
    """
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
