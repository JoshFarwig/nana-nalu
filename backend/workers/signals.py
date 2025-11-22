import logging
from dataclasses import dataclass
from celery import signals

from core import SyncDatabaseManager, SyncRedisManager, SyncHTTPManager, load_settings
from core.config import BaseConfig
from core.logging import configure_logging

from utils.location import Location, get_location

logger = logging.getLogger(__name__)


@dataclass
class WorkerManagers:
    db: SyncDatabaseManager
    redis: SyncRedisManager
    http: SyncHTTPManager


# Global (process scoped) managers
# Settings and location loaded at module import (before fork)
_managers: WorkerManagers | None = None
_settings: BaseConfig = load_settings()
_location: Location = get_location()


@signals.setup_logging.connect
def setup_custom_logging():
    configure_logging()


@signals.worker_process_init.connect
def init_worker_managers(sender=None, **kwargs):
    """
    Initialize worker process resources.

    Called once when each worker process starts (after fork).
    Creates fresh manager instances with connection pools for this worker's lifetime.
    """
    global _managers

    logger.info(
        "Initializing worker process",
        extra={
            "pid": sender.id if sender else None,
            "concurrency": _settings.celery.worker_concurrency,
        },
    )

    _managers = WorkerManagers(
        db=SyncDatabaseManager(_settings.db),
        redis=SyncRedisManager(_settings.redis, _settings.redis.get_cache_url()),
        http=SyncHTTPManager(_settings.http),
    )

    # Health checks
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


def get_settings() -> BaseConfig:
    if _settings is None:
        raise RuntimeError("Settings not initialized")
    return _settings


def get_location() -> Location:
    if _location is None:
        raise RuntimeError("Location not initialized")
    return _location


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
