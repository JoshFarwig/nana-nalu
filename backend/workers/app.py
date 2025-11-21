from celery import Celery

from core import load_settings


def create_celery_app() -> Celery:
    settings = load_settings()

    app = Celery(
        "nana_nalu",
        broker=settings.redis.get_broker_url(),
        backend=settings.redis.get_broker_url(),
    )

    # load config
    app.config_from_object(settings.celery.model_dump())

    return app


app = create_celery_app()
