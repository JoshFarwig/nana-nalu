import asyncio
import logging

from celery.signals import worker_init, worker_shutdown, setup_logging

from core import AsyncDatabaseManager, AsyncRedisManager, get_settings, BaseConfig
from core.logging import configure_logging

logger = logging.getLogger(__name__)


class WorkerState:
    """Singleton resources for a worker instance"""

    # NOTE: the WorkerState singleton is NOT threadsafe.
    # if celery is initialized / cleaned up with a concurrency option that
    # uses multithreading, (i.e. -pool=evenlet) this will need
    # to implement a threading lock to protect race conditions.
    # refer to https://docs.celeryq.dev/en/v5.5.3/userguide/concurrency/index.html
    # for concurrency options avaiable to celery.

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
            # TODO: create http_manager

            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            self.initialized = True
            logger.info("Worker state initialized")

    async def cleanup(self):
        if self.initialized:
            await self.db_manager.close()
            await self.redis_manager.close()
            # TODO: create http_manager
            self.initialized = False


# Worker signals
@worker_init.connect
def init_worker(**kwargs):
    """Initialize worker resources"""
    import os

    env = os.getenv("ENV", "local")
    settings = get_settings(env)
    WorkerState().initialize(settings)


@setup_logging.connect
def setup_logging(**kwargs):
    """Override celery's logging"""
    import os

    env = os.getenv("ENV", "local")
    configure_logging(env)


@worker_shutdown.connect
def shutdown_worker(**kwargs):
    """Cleanup worker resources"""
    state = WorkerState()
    if state.initialized:
        state.loop.run_until_complete(state.cleanup())
