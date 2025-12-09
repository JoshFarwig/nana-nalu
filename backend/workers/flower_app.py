"""
Flower (monitoring UI) entry point.

This module is used by the flower container to create a Celery app instance
with flower-specific configuration (requires only Redis, no DB needed).
"""

from workers.celery_app import create_celery_app

app = create_celery_app(service_type="scheduler")
