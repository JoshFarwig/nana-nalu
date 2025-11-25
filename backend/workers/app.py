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

    # load environment-specific config from Pydantic
    app.config_from_object(settings.celery.model_dump())

    # Application-specific configuration (same across all environments)
    app.conf.update(
        # Serialization
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        # Timezone
        timezone="UTC",
        enable_utc=True,
        # Task routing (organize by queue)
        task_routes={
            "workers.tasks.nwps.*": {"queue": "nwps"},
            "workers.tasks.surfline.*": {"queue": "surfline"},
            "workers.tasks.open_meteo.*": {"queue": "open_meteo"},
        },
    )

    # celery Beat Schedule (periodic tasks)
    app.conf.beat_schedule = {
        # NWPS - runs at 00Z and 12Z (model analysis times)
        "fetch-nwps-maui-00z": {
            "task": "workers.tasks.nwps.fetch_nwps_forecast",
            "schedule": crontab(hour=0, minute=30),  # 30min after model run
            "kwargs": {"location": "maui"},
        },
        "fetch-nwps-maui-12z": {
            "task": "workers.tasks.nwps.fetch_nwps_forecast",
            "schedule": crontab(hour=12, minute=30),
            "kwargs": {"location": "maui"},
        },
        # TODO: add Surfline and Open-Meteo schedules
        # 'fetch-surfline-priority': {
        #     'task': 'workers.tasks.surfline.fetch_surfline_forecasts',
        #     'schedule': crontab(minute='*/10'),
        #     'kwargs': {'priority': 'high'},
        # },
    }

    return app


# create the Celery app instance
app = create_celery_app()

# import signals to register worker lifecycle hooks
# MUST happen after app creation for signals to connect properly
import workers.signals  # noqa: E402, F401

# import tasks to register them with Celery
# Uncomment as you create task modules
from workers.tasks import nwps  # noqa: E402, F401
