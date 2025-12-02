from celery import Celery
from celery.schedules import crontab

from core import load_settings


def create_celery_app() -> Celery:
    """
    Create and configure Celery application.

    Architecture:
    - Tasks are ALWAYS lazy loaded (referenced by string, imported on execution)
    - Worker signals conditionally loaded based on settings.celery.worker
    - Uses prefork pool (multiprocessing) for true CPU parallelism
    - Each worker runs tasks synchronously (no async/await)
    - Worker lifecycle managed via signals in workers/signals.py

    Container modes (controlled via CELERY__WORKER env var):
    - worker (CELERY__WORKER=true): Loads signals, executes tasks with full dependencies
    - beat/flower (CELERY__WORKER=false): Minimal deps, no signals, schedules/monitors only
    """
    settings = load_settings()

    app = Celery(
        "nana_nalu",
        broker=settings.redis.get_broker_url(),
        backend=settings.redis.get_broker_url(),
    )

    app.config_from_object(settings.celery.model_dump())

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_routes={
            "workers.tasks.nwps.*": {"queue": "forecasts"},
        },
    )

    # NOTE: fetching NWPS using a poll-based system for unpredictable model run times
    # parent task dispatches child tasks for all enabled locations
    # ex: HFO timing: early run finishes ~7-9:30 UTC, late run finishes ~17-20 UTC

    # tasks referenced by string (lazy loading), imported by worker on execution
    app.conf.beat_schedule = {
        "nwps-poll-morning": {
            "task": "workers.tasks.nwps.fetch_all_nwps_forecasts",
            "schedule": crontab(hour=10, minute=0),  # 10:00 UTC
        },
        "nwps-poll-evening": {
            "task": "workers.tasks.nwps.fetch_all_nwps_forecasts",
            "schedule": crontab(hour=21, minute=0),  # 21:00 UTC
        },
        "nwps-poll-midday": {
            "task": "workers.tasks.nwps.fetch_all_nwps_forecasts",
            "schedule": crontab(
                hour=14, minute=0
            ),  # 14:00 UTC, catches any straggling forecasts
        },
    }

    # import worker signals / tasks only when running as worker container.
    # allows for beat and flower instances to not have to have eager import
    # resolution and require packages not used by the containers i.e. beat
    # does not need sqlalchemy
    if settings.celery.worker:
        import workers.signals  # noqa: F401
        import workers.tasks.nwps

    return app


# create the Celery app instance
app = create_celery_app()
