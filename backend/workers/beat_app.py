"""
Celery beat (scheduler) entry point.

This module is used by the beat container to create a Celery app instance
with scheduler-specific configuration (requires only Redis, no DB needed).
"""

from workers.celery_app import create_celery_app

app = create_celery_app(service_type="scheduler")
