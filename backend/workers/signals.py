from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from celery import signals

from core.config import WorkerSettings, load_settings
from core.logging import configure_logging

from utils.region import Region, get_enabled_regions


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.database import SyncDatabaseManager
    from core.redis import SyncRedisManager
    from core.http import SyncHTTPManager


@dataclass
class WorkerManagers:
    db: SyncDatabaseManager
    redis: SyncRedisManager
    http: SyncHTTPManager


# global (process scoped) managers
# settings and locations loaded at module import (before fork)
# NOTE: This module is only imported by worker containers via workers/worker_app.py
_managers: WorkerManagers | None = None
_settings: WorkerSettings = load_settings("worker")
_regions: frozenset[Region] = get_enabled_regions()


@signals.setup_logging.connect
def setup_custom_logging(sender=None, **kwargs):
    configure_logging()


@signals.worker_process_init.connect
def init_worker_managers(sender=None, **kwargs):
    """
    Initialize worker process resources.

    Called once when each worker process starts (after fork).
    Creates fresh manager instances with connection pools for this worker's lifetime.
    """
    from core.database import SyncDatabaseManager
    from core.redis import SyncRedisManager
    from core.http import SyncHTTPManager

    global _managers

    logger.info(
        "Initializing worker process",
        extra={
            "concurrency": _settings.celery.worker_concurrency,
        },
    )

    _managers = WorkerManagers(
        db=SyncDatabaseManager(_settings.db),
        redis=SyncRedisManager(_settings.redis, _settings.redis.get_cache_url()),
        http=SyncHTTPManager(_settings.http, retry=False),
    )

    # health checks
    if not _managers.db.health_check():
        logger.error("Database health check failed on worker init")
    if not _managers.redis.health_check():
        logger.error("Redis health check failed on worker init")

    logger.info("Worker resource managers initialized successfully")


@signals.worker_process_shutdown.connect
def shutdown_worker_managers(sender=None, **kwargs):
    """
    Clean up worker process resources.

    Called when worker process is shutting down (after max_tasks_per_child).
    Closes all connection pools and disposes engines.
    """
    global _managers

    logger.info("Shutting down worker process")

    if _managers:
        for name, manager in _managers.__dict__.items():
            if manager is not None:
                try:
                    logger.info(f"Closing {name} manager")
                    manager.close()
                except Exception:
                    logger.exception(f"Error closing {name} manager")

        _managers = None
        logger.info("Worker managers shutdown complete")


def get_worker_settings() -> WorkerSettings:
    return _settings


def get_worker_regions() -> set[Region]:
    return _regions


def get_worker_managers() -> WorkerManagers:
    if _managers is None:
        raise RuntimeError(
            "Worker managers not initialized. "
            "This should only be called from within Celery Tasks"
        )
    return _managers


def get_db_manager() -> SyncDatabaseManager:
    return get_worker_managers().db


def get_redis_manager() -> SyncRedisManager:
    return get_worker_managers().redis


def get_http_manager() -> SyncHTTPManager:
    return get_worker_managers().http
