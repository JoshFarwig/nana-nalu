"""
Celery worker entry point.

This module is used by the worker container to create a Celery app instance
with worker-specific configuration (requires DB + Redis for task execution).
"""

from workers.celery_app import create_celery_app

app = create_celery_app(service_type="worker")
