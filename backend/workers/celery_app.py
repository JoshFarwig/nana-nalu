from celery import Celery
from celery.schedules import crontab

from core import load_settings


def create_celery_app(service_type: str = "worker") -> Celery:
    """
    Create and configure Celery application.

    Architecture:
    - Tasks are ALWAYS lazy loaded (referenced by string, imported on execution)
    - Worker signals conditionally loaded based on service_type
    - Uses prefork pool (multiprocessing) for true CPU parallelism
    - Each worker runs tasks synchronously (no async/await)
    - Worker lifecycle managed via signals in workers/signals.py

    Service types:
    - worker: Executes tasks, needs DB + Redis, loads signals and task modules
    - scheduler: Celery beat, needs only Redis, no signals/task imports
    - flower: Monitoring UI, needs only Redis, no signals/task imports

    Args:
        service_type: Type of Celery service ("worker", "scheduler", or "flower")
    """
    settings = load_settings(service_type)

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
    # and flower do not need sqlalchemy
    if service_type == "worker":
        import workers.signals  # noqa: F401
        import workers.tasks.nwps

    return app
