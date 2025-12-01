from celery import Celery
from celery.schedules import crontab

from core import load_settings


def create_celery_app() -> Celery:
    """
    Create and configure Celery application.

    Architecture:
    - Uses prefork pool (multiprocessing) for true CPU parallelism
    - Each worker runs tasks synchronously (no async/await)
    - Worker lifecycle managed via signals in workers/signals.py
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
            "workers.tasks.nwps.*": {"queue": "nwps"},
        },
    )

    # NOTE: fetching NWPS using a poll-based system for unpredictable model run times
    # parent task dispatches child tasks for all enabled locations
    # ex: HFO timing: early run finishes ~7-9:30 UTC, late run finishes ~17-20 UTC

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

    return app


# create the Celery app instance
app = create_celery_app()

# import signals to register worker lifecycle hooks
# MUST happen after app creation for signals to connect properly
import workers.signals  # noqa: E402, F401

# import tasks to register them with Celery
# uncomment as you create task modules
from workers.tasks import nwps  # noqa: E402, F401
