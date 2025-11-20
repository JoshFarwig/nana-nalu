import logging

from celery.signals import worker_init, worker_shutdown, setup_logging

from core import (
    SyncDatabaseManager,
    SyncRedisManager,
    SyncHTTPManager,
    get_settings,
)

from core.logging import configure_logging

logger = logging.getLogger(__name__)


# Worker signals
@worker_init.connect
def init_worker(**kwargs):
    """Initialize worker resources"""


@setup_logging.connect
def setup_celery_logging(**kwargs):
    """Override celery's logging configuration"""


@worker_shutdown.connect
def shutdown_worker(**kwargs):
    """Cleanup worker resources"""
