import os

from celery import Celery

from core import get_settings


def create_celery_app() -> Celery:
    """Create and configure Celery app"""

    env = os.getenv("ENV", "local")
    settings = get_settings(env)

    # create celery app
    app = Celery(
        "nana_nalu",
        broker=settings.redis.get_broker_url(),
        backend=settings.redis.get_broker_url(),
    )

    # load config
    app.config_from_object(settings.celery.model_dump())

    return app


app = create_celery_app()
