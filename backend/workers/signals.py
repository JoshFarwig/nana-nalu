import logging
from dataclasses import dataclass
from celery import signals

from core import SyncDatabaseManager, SyncRedisManager, SyncHTTPManager, load_settings
from core.config import BaseConfig
from core.logging import configure_logging

logger = logging.getLogger(__name__)


@dataclass
class WorkerManagers:
    db: SyncDatabaseManager
    redis: SyncRedisManager
    http: SyncHTTPManager


# global (process scoped) managers and settings
_managers: WorkerManagers | None = None
_settings = load_settings()


@signals.setup_logging.connect
def setup_custom_logging():
    configure_logging()


@signals.worker_process_init.connect
def init_worker_managers(sender=None, **kwargs):
    global _managers
    global _settings

    _managers = WorkerManagers(
        db=SyncDatabaseManager(_settings.db),
        redis=SyncRedisManager(_settings.redis, _settings.redis.get_cache_url()),
        http=SyncHTTPManager(_settings.http),
    )

    logger.info(
        "Worker managers initialized",
        extra={
            "pid": sender.id if sender else None,
            "concurrency": _settings.celery.worker_concurrency,
        },
    )


@signals.worker_process_shutdown.connect
def shutdown_worker_managers(sender=None, **kwargs):
    global _managers

    if _managers:
        for name, manager in _managers.__dict__.items():
            try:
                manager.close()
                logger.info(f"{name} manager closed")
            except Exception:
                logger.exception(f"Error closing {name} manager")

        _managers = None
        logger.info("Worker managers shutdown complete")


def get_settings() -> BaseConfig:
    if _settings is None:
        raise RuntimeError("Settings not initialized")
    return _settings


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
