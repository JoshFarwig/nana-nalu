import asyncio
import logging

from celery.signals import worker_init, worker_shutdown, setup_logging

from core import AsyncDatabaseManager, AsyncRedisManager, get_settings, BaseConfig
from core.http import AsyncHTTPManager
from core.logging import configure_logging

logger = logging.getLogger(__name__)


class WorkerState:
    """Singleton resources for a worker instance"""

    # NOTE: this singleton is process-isolated when using
    # prefork pool as each worker process gets its own instance.
    # with eventlet/gevent, greenlets run in a single thread (no race conditions),
    # but mixing asyncio with greenlets requires careful locking mechanisms
    # (may need implemement this in the future)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def initialize(self, settings: BaseConfig):
        if not self.initialized:
            self.settings = settings
            self.db_manager = AsyncDatabaseManager(settings.db)
            self.redis_manager = AsyncRedisManager(
                settings.redis, settings.redis.get_cache_url()
            )
            self.http_manager = AsyncHTTPManager(settings.http)

            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            self.initialized = True
            logger.info("Worker state initialized")

    async def cleanup(self):
        if self.initialized:
            await self.db_manager.close()
            await self.redis_manager.close()
            await self.http_manager.close()
            self.initialized = False


# Worker signals
@worker_init.connect
def init_worker(**kwargs):
    """Initialize worker resources"""
    settings = get_settings()
    WorkerState().initialize(settings)


@setup_logging.connect
def setup_celery_logging(**kwargs):
    """Override celery's logging configuration"""
    configure_logging()


@worker_shutdown.connect
def shutdown_worker(**kwargs):
    """Cleanup worker resources"""
    state = WorkerState()
    if state.initialized:
        state.loop.run_until_complete(state.cleanup())
