# Celery + FastAPI Shared Async Architecture

## Executive Summary

This document outlines the **correct, production-tested architecture** for sharing async code between FastAPI and Celery, based on:
- SQLAlchemy official async documentation
- Industry patterns (Apache Superset, Django-Celery)
- Medium article "Solving SQLAlchemy Connection Issues in Celery Workers" by Ryan Zheng
- Real-world Celery + async integration challenges

**Key Principle**: Use async code everywhere (DB, Redis, repositories, services), but wrap Celery tasks in `asyncio.run()` and use `worker_process_init` signal for proper engine isolation.

---

## The Problem: Naive Async + Celery Integration

### ❌ What Doesn't Work

Many tutorials suggest this approach, which **appears** to work but has critical issues:

```python
# ❌ WRONG: Global singleton with event loop
class WorkerState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.loop = asyncio.new_event_loop()  # ← Created once
            cls._instance.db_manager = AsyncDatabaseManager(...)  # ← Shared
        return cls._instance

@signals.worker_init.connect  # ← Wrong signal (runs in parent process)
def init_worker(**kwargs):
    WorkerState().initialize(settings)

class AsyncTask(Task):
    def __call__(self, *args, **kwargs):
        state = WorkerState()
        return state.loop.run_until_complete(...)  # ← Conflicts with Celery
```

### Why This Fails

1. **Event Loop Conflicts**
   - Celery internally uses `asyncio.run()` for async tasks
   - Your custom loop conflicts with Celery's loop
   - Results in `RuntimeError: This event loop is already running`

2. **Process Boundary Issues (Prefork Pool)**
   - `worker_init` runs in **parent process** before fork
   - All child processes **share the same AsyncEngine**
   - SQLAlchemy explicitly warns: "database connections should not travel across process boundaries"
   - Results in `SSL connection has been closed unexpectedly`, transaction conflicts

3. **AsyncEngine Event Loop Binding**
   - `AsyncEngine` binds to the event loop active when created
   - If created before tasks run, binds to wrong loop
   - Results in `Queue is bound to a different event loop`

4. **Connection Pool Corruption**
   - Multiple processes try to use same connection objects
   - PostgreSQL connection state gets corrupted
   - Results in `PGRES_TUPLES_OK error`, `transaction already in progress`

---

## ✅ The Correct Pattern: Process-Local Engines + worker_process_init

Based on production-proven patterns from the Medium article and SQLAlchemy community.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Main Process (Before Fork)                                  │
│ - Default AsyncEngine for FastAPI                           │
│ - No worker engines yet                                     │
└─────────────────────────────────────────────────────────────┘
                            │
                         fork()
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ Worker 1      │  │ Worker 2      │  │ Worker 3      │
│               │  │               │  │               │
│ Event Loop A  │  │ Event Loop B  │  │ Event Loop C  │
│ Engine A      │  │ Engine B      │  │ Engine C      │
│ Pool (2 conn) │  │ Pool (2 conn) │  │ Pool (2 conn) │
└───────────────┘  └───────────────┘  └───────────────┘
```

### Key Principles

1. **One AsyncEngine per worker process** (not per task, not shared)
2. **Create engines AFTER fork** using `worker_process_init` signal
3. **Use `threading.local()` for process isolation**
4. **Let Celery handle event loops** via `asyncio.run()`
5. **Tasks are sync wrappers** around async implementation

---

## Implementation

### 1. Database Manager (Shared by FastAPI & Celery)

```python
# backend/core/database.py
from threading import local
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from .configs import DatabaseConfig
import logging

logger = logging.getLogger(__name__)

# Process-local storage (survives fork correctly)
process_local = local()

# Default engine for main process (FastAPI)
default_engine: AsyncEngine | None = None
default_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_default_engine(settings: DatabaseConfig) -> AsyncEngine:
    """
    Create default engine for main process (FastAPI).
    Called during app startup.
    """
    global default_engine, default_session_factory

    logger.info("Creating default AsyncEngine for main process (FastAPI)")

    default_engine = create_async_engine(
        settings.get_async_url(),
        pool_size=settings.async_pool_size,  # 5-10 for FastAPI
        max_overflow=settings.async_max_overflow,
        pool_timeout=settings.async_pool_timeout,
        pool_pre_ping=True,
    )

    default_session_factory = async_sessionmaker(
        default_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return default_engine


async def create_engine_for_worker(settings: DatabaseConfig) -> AsyncEngine:
    """
    Create a new AsyncEngine for a worker process.

    Called from worker_process_init signal AFTER fork.
    Each worker process gets its own isolated engine and connection pool.
    """
    logger.info("Creating AsyncEngine for Celery worker process")

    # Create engine in current event loop (created by worker_process_init)
    engine = create_async_engine(
        settings.get_async_url(),
        pool_size=2,  # Small pool for Celery workers (2-3 connections)
        max_overflow=3,
        pool_timeout=30,
        pool_pre_ping=True,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Store in process-local storage
    process_local.engine = engine
    process_local.session_factory = session_factory

    logger.info(f"Worker process AsyncEngine created (pool_size=2)")

    return engine


async def dispose_engine() -> None:
    """
    Dispose of the process-local engine if it exists.
    Called from worker_process_shutdown signal.
    """
    if hasattr(process_local, 'engine'):
        logger.info("Disposing AsyncEngine for Celery worker process")
        await process_local.engine.dispose()
        del process_local.engine
        del process_local.session_factory


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get the appropriate session factory for the current process.

    - In Celery worker: Returns process-local factory
    - In FastAPI: Returns default factory
    """
    # Check if we have a process-local factory (Celery worker)
    if hasattr(process_local, 'session_factory'):
        return process_local.session_factory

    # Otherwise, use default factory (FastAPI)
    if default_session_factory is None:
        raise RuntimeError(
            "Default session factory not initialized. "
            "Call create_default_engine() during app startup."
        )

    return default_session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session (works for both FastAPI and Celery).

    Usage in FastAPI:
        async with get_session() as session:
            # use session

    Usage in Celery:
        async def _task_impl():
            async with get_session() as session:
                # use session

        @app.task
        def my_task():
            return asyncio.run(_task_impl())
    """
    factory = get_session_factory()

    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def health_check() -> bool:
    """Check if database connection is healthy."""
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
```

### 2. Celery Worker Signals (Critical!)

```python
# backend/workers/signals.py
from celery.signals import worker_process_init, worker_process_shutdown
from core.database import create_engine_for_worker, dispose_engine
from core.redis import create_redis_for_worker, dispose_redis  # Similar pattern
from core.configs import get_settings
import asyncio
import logging

logger = logging.getLogger(__name__)


@worker_process_init.connect
def init_worker_process(*args, **kwargs):
    """
    Initialize resources for a Celery worker process.

    CRITICAL: This signal handler runs in EACH forked child process,
    creating a separate AsyncEngine for each worker.

    This runs AFTER the fork, ensuring proper process isolation.
    """
    logger.info("=" * 60)
    logger.info("Initializing Celery worker process")
    logger.info("=" * 60)

    # Create new event loop for this worker process
    # (Celery will use this loop for asyncio.run() calls)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logger.info("Created new event loop for worker process")

    # Load settings
    settings = get_settings()

    # Create AsyncEngine in this event loop
    loop.run_until_complete(create_engine_for_worker(settings.db))
    logger.info("Created AsyncEngine for worker process")

    # Create Redis connection pool in this event loop (if using async Redis)
    loop.run_until_complete(create_redis_for_worker(settings.redis))
    logger.info("Created Redis pool for worker process")

    logger.info("Worker process initialization complete")
    logger.info("=" * 60)


@worker_process_shutdown.connect
def shutdown_worker_process(*args, **kwargs):
    """
    Clean up resources for a Celery worker process.

    Runs when a worker process is shutting down.
    Properly disposes of AsyncEngine to release database connections.
    """
    logger.info("=" * 60)
    logger.info("Shutting down Celery worker process")
    logger.info("=" * 60)

    loop = asyncio.get_event_loop()

    # Dispose AsyncEngine
    try:
        loop.run_until_complete(dispose_engine())
        logger.info("Disposed AsyncEngine for worker process")
    except Exception as e:
        logger.error(f"Error disposing AsyncEngine: {e}")

    # Dispose Redis pool (if using async Redis)
    try:
        loop.run_until_complete(dispose_redis())
        logger.info("Disposed Redis pool for worker process")
    except Exception as e:
        logger.error(f"Error disposing Redis pool: {e}")

    logger.info("Worker process shutdown complete")
    logger.info("=" * 60)
```

### 3. Celery App Setup

```python
# backend/workers/app.py
from celery import Celery
from core.configs import get_settings

settings = get_settings()

app = Celery(
    'nana_nalu',
    broker=settings.redis.broker_url.get_secret_value(),
    backend=settings.redis.broker_url.get_secret_value(),
)

app.conf.update(
    # Task execution
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Worker configuration
    worker_pool='prefork',  # Use prefork (default) for CPU-bound tasks
    worker_concurrency=4,    # Number of worker processes (adjust based on CPU cores)
    worker_prefetch_multiplier=1,  # Fetch 1 task at a time (prevents starvation)
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (prevents memory leaks)

    # Result backend
    result_expires=3600,  # 1 hour

    # Task routes
    task_routes={
        'workers.tasks.forecast.*': {'queue': 'forecast'},
        'workers.tasks.maintenance.*': {'queue': 'maintenance'},
    },
)

# Import tasks to register them
from workers.tasks import forecast  # noqa
```

### 4. Celery Tasks (Sync Wrappers Around Async Code)

```python
# backend/workers/tasks/forecast.py
from celery import shared_task
from core.database import get_session
from core.redis import get_redis
from repositories.surf_spot_repository import SurfSpotRepository
from services.forecast.providers.nwps.provider import NWPSProvider
from services.http import AsyncHTTPManager
import asyncio
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def fetch_nwps_forecasts(self, region: str):
    """
    Fetch NWPS forecasts for all spots in a region.

    This is a SYNC function (Celery requirement), but it calls
    async implementation using asyncio.run().

    Celery will execute this in a worker process that has:
    - Its own event loop (created by worker_process_init)
    - Its own AsyncEngine (process-local via threading.local)
    - Its own Redis pool (process-local)
    """
    try:
        logger.info(f"Starting NWPS forecast fetch for region: {region}")
        result = asyncio.run(_fetch_nwps_async(region))
        logger.info(f"Completed NWPS forecast fetch for region: {region}")
        return result
    except Exception as e:
        logger.error(f"Error fetching NWPS forecasts: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e)


async def _fetch_nwps_async(region: str) -> dict:
    """
    Async implementation of NWPS forecast fetching.

    This function reuses ALL async code from FastAPI:
    - Async repositories
    - Async database sessions
    - Async HTTP clients
    - Async providers
    """
    # Use process-local AsyncEngine via get_session()
    async with get_session() as session:
        # Async repository (shared with FastAPI)
        repo = SurfSpotRepository(session)
        spots = await repo.get_all_in_grid(
            min_lat=20.5,
            max_lat=21.2,
            min_lon=-157.0,
            max_lon=-156.0,
        )

        logger.info(f"Found {len(spots)} spots for NWPS forecast")

        # Async HTTP manager (could be process-local too if needed)
        http_manager = AsyncHTTPManager()

        try:
            # Async provider (shared with FastAPI)
            provider = NWPSProvider(
                config=get_nwps_config(region),
                http_manager=http_manager,
                spot_repository=repo,
            )

            # Download file (async I/O)
            analysis_time = datetime.now(timezone.utc)
            file_path = await provider.download_file(analysis_time)

            logger.info(f"Downloaded NWPS file: {file_path}")

            # Extract forecasts (async, uses asyncio.to_thread internally)
            forecasts = await provider.extract_forecasts(file_path)

            logger.info(f"Extracted forecasts for {len(forecasts)} spots")

            # Store in Redis (async)
            redis = await get_redis()
            for spot_id, forecast_data in forecasts.items():
                key = f"forecast:nwps:{spot_id}:{analysis_time.isoformat()}"
                await redis.set(key, json.dumps(forecast_data), ex=50400)  # 14 hours

            logger.info(f"Stored forecasts in Redis")

            # Cleanup file
            if file_path.exists():
                file_path.unlink()

            return {
                'region': region,
                'spots_processed': len(forecasts),
                'analysis_time': analysis_time.isoformat(),
            }

        finally:
            # Close HTTP client
            await http_manager.close()


@shared_task
def fetch_gfs_forecasts(region: str):
    """Fetch GFS wave forecasts."""
    return asyncio.run(_fetch_gfs_async(region))


async def _fetch_gfs_async(region: str) -> dict:
    """Async implementation for GFS."""
    async with get_session() as session:
        # Similar pattern...
        pass


@shared_task
def fetch_surfline_forecasts(priority: str = 'all'):
    """Fetch Surfline forecasts."""
    return asyncio.run(_fetch_surfline_async(priority))


async def _fetch_surfline_async(priority: str) -> dict:
    """Async implementation for Surfline."""
    async with get_session() as session:
        # Similar pattern...
        pass
```

### 5. FastAPI Startup (Initialize Default Engine)

```python
# backend/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from core.database import create_default_engine
from core.configs import get_settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager."""
    # Startup
    settings = get_settings()

    # Create default engine for FastAPI
    create_default_engine(settings.db)

    yield

    # Shutdown
    # (engines will be disposed automatically)

app = FastAPI(lifespan=lifespan)
```

---

## Celery Beat Schedule

```python
# backend/workers/app.py (continued)
from celery.schedules import crontab

app.conf.beat_schedule = {
    # NWPS - Runs at 00Z and 12Z (add 30min delay for NOAA processing)
    'fetch-nwps-maui-00z': {
        'task': 'workers.tasks.forecast.fetch_nwps_forecasts',
        'schedule': crontab(hour=0, minute=30),
        'kwargs': {'region': 'maui'},
    },
    'fetch-nwps-maui-12z': {
        'task': 'workers.tasks.forecast.fetch_nwps_forecasts',
        'schedule': crontab(hour=12, minute=30),
        'kwargs': {'region': 'maui'},
    },

    # GFS - Every 6 hours
    'fetch-gfs-maui': {
        'task': 'workers.tasks.forecast.fetch_gfs_forecasts',
        'schedule': crontab(hour='*/6', minute=0),
        'kwargs': {'region': 'maui'},
    },

    # Surfline - Priority spots every 10min, all spots every 3 hours
    'fetch-surfline-priority': {
        'task': 'workers.tasks.forecast.fetch_surfline_forecasts',
        'schedule': crontab(minute='*/10'),
        'kwargs': {'priority': 'high'},
    },
    'fetch-surfline-all': {
        'task': 'workers.tasks.forecast.fetch_surfline_forecasts',
        'schedule': crontab(hour='*/3', minute=0),
        'kwargs': {'priority': 'all'},
    },
}
```

---

## Running Celery

```bash
# Worker (with prefork pool)
celery -A workers.app worker --loglevel=info --concurrency=4

# Beat (scheduler)
celery -A workers.app beat --loglevel=info

# Combined (development only)
celery -A workers.app worker --beat --loglevel=info --concurrency=2
```

---

## Key Benefits of This Architecture

### ✅ Code Reuse
- **100% async code reuse** between FastAPI and Celery
- Same repositories, services, providers
- No duplicate sync versions needed

### ✅ Correct Process Isolation
- Each worker process has its own AsyncEngine
- Created **after fork** via `worker_process_init`
- No shared connections across processes

### ✅ Proper Connection Pooling
- FastAPI: Larger pool (5-10 connections) for high concurrency
- Celery workers: Small pool (2-3 connections) per worker
- Total connections = workers × pool_size (e.g., 4 workers × 2 = 8 connections)

### ✅ Works with Prefork Pool
- Scales horizontally with multiple worker processes
- Each worker runs tasks in parallel
- Proper resource cleanup on shutdown

### ✅ Event Loop Handling
- Celery manages event loops via `asyncio.run()`
- No conflicts with custom loops
- Clean, predictable behavior

### ✅ asyncio.to_thread() Benefits
- CPU-bound work (GRIB parsing, xarray ops) runs in thread pool
- Doesn't block event loop
- Allows concurrent I/O while processing

---

## Common Mistakes to Avoid

### ❌ Don't: Create Engine at Import Time
```python
# ❌ WRONG
engine = create_async_engine(...)  # Created before fork

# ✅ CORRECT
# Use worker_process_init signal
```

### ❌ Don't: Use worker_init Signal
```python
# ❌ WRONG
@signals.worker_init.connect  # Runs in parent process
def init(**kwargs):
    create_engine()

# ✅ CORRECT
@signals.worker_process_init.connect  # Runs in each child
def init(**kwargs):
    asyncio.run(create_engine_for_worker())
```

### ❌ Don't: Create Singleton Event Loop
```python
# ❌ WRONG
class WorkerState:
    loop = asyncio.new_event_loop()  # Conflicts with Celery

# ✅ CORRECT
# Let Celery handle event loops via asyncio.run()
```

### ❌ Don't: Share Engine Across Processes
```python
# ❌ WRONG
global_engine = create_async_engine(...)  # Shared

# ✅ CORRECT
process_local.engine = create_async_engine(...)  # Isolated
```

---

## Performance Considerations

### Connection Pool Sizing

**FastAPI** (main process):
```python
pool_size=10         # 10 persistent connections
max_overflow=20      # 20 additional on demand
# Total: 30 max concurrent connections
```

**Celery workers** (4 processes):
```python
pool_size=2          # 2 persistent per worker
max_overflow=3       # 3 additional per worker
# Total per worker: 5 max
# Total all workers: 4 × 5 = 20 max concurrent connections
```

**Database total**: 30 (FastAPI) + 20 (Celery) = 50 connections max

### Task Execution Time

With prefork pool (4 workers):
- Task A (NWPS): 30 seconds
- Task B (GFS): 45 seconds
- Task C (Surfline): 15 seconds

**Sequential**: 30 + 45 + 15 = 90 seconds
**Parallel** (separate tasks): max(30, 45, 15) = 45 seconds

**Recommendation**: Use separate tasks for each provider, let prefork pool parallelize.

---

## Monitoring & Debugging

### Logging

```python
# Enable SQL logging in Celery workers
create_async_engine(
    url,
    echo=True,  # Log all SQL statements
)
```

### Flower (Celery monitoring)

```bash
pip install flower
celery -A workers.app flower --port=5555
```

Visit http://localhost:5555

### Check Worker Resources

```python
@shared_task
def health_check():
    """Check worker health."""
    return asyncio.run(_health_check_async())

async def _health_check_async():
    db_healthy = await database.health_check()
    redis_healthy = await redis.health_check()

    return {
        'database': db_healthy,
        'redis': redis_healthy,
        'pid': os.getpid(),
    }
```

---

## Summary

This architecture provides:
- ✅ Correct process isolation for AsyncEngine
- ✅ 100% async code reuse (no duplication)
- ✅ Production-proven pattern (Medium article, SQLAlchemy docs)
- ✅ Scales with prefork pool
- ✅ Proper resource lifecycle management
- ✅ Clean separation between FastAPI and Celery concerns

**The key insight**: Tasks are sync wrappers (`asyncio.run()`) around async implementations, with process-local engines created after fork using `worker_process_init`.

---

## References & Sources

This architecture is based on extensive research from official documentation, GitHub discussions, Stack Overflow, and production implementations.

### Primary Sources

**1. Medium Article (Production Pattern)**
- **Title**: "Solving SQLAlchemy Connection Issues in Celery Workers"
- **Author**: Ryan Zheng
- **Date**: May 2, 2025
- **URL**: https://ryan-zheng.medium.com/solving-sqlalchemy-connection-issues-in-celery-workers-9d7cbf299221
- **Key contribution**: Production-tested pattern using `threading.local()` and `worker_process_init`

### Official Documentation

**2. Celery Signals**
- **URL**: https://docs.celeryq.dev/en/stable/userguide/signals.html
- **Relevant sections**: `worker_init`, `worker_process_init`, `worker_process_shutdown`
- **Key insight**: `worker_process_init` runs in each child process after fork

**3. Celery Concurrency**
- **URL**: https://docs.celeryq.dev/en/latest/userguide/concurrency/index.html
- **Topic**: Worker pool types (prefork, solo, threads, gevent, eventlet)

**4. Celery Prefork Pool Implementation**
- **URL**: https://docs.celeryq.dev/en/stable/internals/reference/celery.concurrency.prefork.html
- **Topic**: Internal implementation details

**5. SQLAlchemy Async I/O**
- **URL**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Relevant sections**: AsyncEngine lifecycle, event loop binding, disposal
- **Key quote**: "AsyncEngine cannot properly dispose of connections within `__del__`. Failing to explicitly dispose may result in 'RuntimeError: Event loop is closed' warnings."

### GitHub Discussions - Celery

**6. celery/celery #9058** - "The way to run async functions in Celery tasks in one event loop"
- **URL**: https://github.com/celery/celery/discussions/9058
- **Topic**: Problems with `asgiref.async_to_sync()` creating new event loops
- **Key finding**: Creates new loop each time, breaks SQLAlchemy session pools
- **Solution discussed**: Custom background event loop thread (complex, not recommended)

**7. celery/celery #7573** - "Emit signal.worker_init in prefork pool child process"
- **URL**: https://github.com/celery/celery/issues/7573
- **Topic**: Signal behavior differences between `worker_init` and `worker_process_init`
- **Critical finding**: `worker_init` does NOT run in child processes (runs in parent)
- **Solution**: Always use `worker_process_init` for per-process initialization

**8. celery/celery #7466** - "How/when does celery create an event loop when using the gevent pool?"
- **URL**: https://github.com/celery/celery/discussions/7466
- **Topic**: Event loop creation with different worker pools

**9. celery/celery #5405** - "worker_process_init and solo concurrency"
- **URL**: https://github.com/celery/celery/issues/5405
- **Topic**: Signal behavior with solo vs prefork pools

### GitHub Discussions - SQLAlchemy

**10. sqlalchemy/sqlalchemy #11507** - "Event loop closing when reusing an AsyncEngine"
- **URL**: https://github.com/sqlalchemy/sqlalchemy/discussions/11507
- **Topic**: AsyncEngine event loop binding issues
- **Key problem**: Engine created in one event loop, used in another
- **Error**: "Queue is bound to a different event loop"

**11. sqlalchemy/sqlalchemy #9388** - "Sqlalchemy with distributed task (Celery)"
- **URL**: https://github.com/sqlalchemy/sqlalchemy/discussions/9388
- **Topic**: How to properly use SQLAlchemy with Celery
- **Recommendation**: Use `worker_process_init` to dispose/recreate engines after fork

**12. sqlalchemy/sqlalchemy #5980** - "Performing AsyncIO pooling in SQLAlchemy"
- **URL**: https://github.com/sqlalchemy/sqlalchemy/discussions/5980
- **Topic**: Async connection pooling strategies

### Production Implementations

**13. apache/superset #13350** - "Reset DB connection pools for forked worker processes"
- **URL**: https://github.com/apache/superset/pull/13350
- **Project**: Apache Superset (major open-source BI tool)
- **Implementation**: Shows real-world usage of `worker_process_init` pattern
- **Code**: Disposes SQLAlchemy engine in child processes after fork

### Stack Overflow Discussions

**14. "How to combine Celery with asyncio?"**
- **URL**: https://stackoverflow.com/questions/39815771/how-to-combine-celery-with-asyncio
- **Views**: High traffic question
- **Topic**: General patterns for Celery + async integration
- **Key answers**: `loop.run_until_complete()` pattern

**15. "Is there an easier way to run async functions in Celery tasks in one event loop?"**
- **URL**: https://stackoverflow.com/questions/78570189/is-there-an-easier-way-to-run-async-functions-in-celery-tasks-in-one-event-loop
- **Date**: 2024 (recent)
- **Topic**: User struggling with background event loop approach
- **Consensus**: Complex problem, no official Celery solution yet

**16. "Event loop is closed in a celery worker"**
- **URL**: https://stackoverflow.com/questions/74058894/event-loop-is-closed-in-a-celery-worker
- **Topic**: Common error when AsyncEngine outlives event loop
- **Solution**: Proper disposal in `worker_process_shutdown`

**17. "What's the proper way to use SQLAlchemy Sessions with Celery?"**
- **URL**: https://stackoverflow.com/questions/64016062/whats-the-proper-way-to-use-sqlalchemy-sessions-with-celery
- **Topic**: Sync SQLAlchemy + Celery (establishes baseline pattern)
- **Accepted answer**: Use `worker_process_init` signal

**18. "PostgreSQL Connection Issues: 'Queue is bound to a different event loop' in Async Celery Task"**
- **URL**: https://stackoverflow.com/questions/78875393/postgresql-connection-issues-remaining-connection-slots-are-reserved-queue
- **Date**: 2024 (very recent)
- **Error**: Classic AsyncEngine + Celery problem
- **Cause**: Engine created in different event loop than task execution

**19. "Celery Worker Database Connection Pooling"**
- **URL**: https://stackoverflow.com/questions/14526249/celery-worker-database-connection-pooling
- **Topic**: Connection pool management with prefork
- **Key insight**: Each worker process needs its own pool

**20. "Celery how to establish async connection per worker"**
- **URL**: https://stackoverflow.com/questions/68430582/python-celery-how-to-establish-async-connection-per-worker
- **Topic**: Per-worker async resource initialization

### Blog Posts & Articles

**21. "Not The Same Pre-fork Worker Model"**
- **Author**: Yang Wang
- **URLs**:
  - https://www.yangster.ca/post/not-the-same-pre-fork-worker-model/
  - https://medium.com/nepfin-engineering/not-the-same-pre-fork-worker-model-dde184feefa1
- **Topic**: Differences between Gunicorn and Celery prefork models

**22. "SQLAlchemy connection pool within multiple threads and processes"**
- **Author**: David Caron
- **URL**: https://davidcaron.dev/sqlalchemy-multiple-threads-and-processes/
- **Topic**: Thread and process safety with SQLAlchemy pools

### Community Forums

**23. SQLAlchemy Google Group - "Using a connection pool with multiple processes"**
- **URL**: https://groups.google.com/g/sqlalchemy/c/YX9NuBD75oY
- **Topic**: Process boundaries and connection pools
- **Key insight**: Connections are file descriptors and don't survive fork

**24. Celery Users Mailing List - "per-worker initialization to prevent shared SQL connection pools?"**
- **URL**: https://celery-users.narkive.com/einPxD2K/per-worker-initialization-to-prevent-shared-sql-connection-pools
- **Topic**: Historical discussion on worker initialization patterns

### Other Documentation

**25. Celery School - "Celery Execution Pools: What is it all about?"**
- **URL**: https://celery.school/celery-worker-pools
- **Topic**: Deep dive into worker pool implementations

**26. Celery School - "The Worker and the Pool"**
- **URL**: https://celery.school/the-worker-and-the-pool
- **Topic**: Worker architecture and pool management

**27. Vultr Docs - "Asynchronous Task Queueing in Python using Celery"**
- **URL**: https://docs.vultr.com/asynchronous-task-queueing-in-python-using-celery
- **Topic**: General Celery async patterns

**28. TestDriven.io - "Asynchronous Tasks with FastAPI and Celery"**
- **URL**: https://testdriven.io/blog/fastapi-and-celery/
- **Topic**: FastAPI + Celery integration patterns

### Key Consensus Findings

Across all sources, the following pattern emerged as the correct approach:

1. ✅ Use `worker_process_init` signal (NOT `worker_init`)
2. ✅ Use `threading.local()` for process isolation
3. ✅ Create AsyncEngine AFTER fork in each child process
4. ✅ Use `asyncio.run()` in tasks (NOT `asgiref.async_to_sync()`)
5. ✅ Dispose engine in `worker_process_shutdown`
6. ✅ Small connection pools for Celery (2-3 connections per worker)

### Anti-Patterns to Avoid

These were consistently identified as problematic across sources:

1. ❌ Creating engine at import time (before fork)
2. ❌ Using `worker_init` signal (runs in parent process)
3. ❌ Sharing engines across processes
4. ❌ Using custom WorkerState singleton with persistent event loop
5. ❌ Using `asgiref.async_to_sync()` (creates new loop per call)
6. ❌ Not disposing engines on shutdown

### Additional Reading

For deeper understanding of the underlying issues:

- Python multiprocessing and fork behavior
- Unix process forking and file descriptor inheritance
- PostgreSQL connection protocol and process boundaries
- asyncio event loop lifecycle
- SQLAlchemy connection pooling internals
- Thread-local storage in Python (`threading.local()`)

---

## Acknowledgments

This architecture document synthesizes knowledge from:
- SQLAlchemy maintainers (Mike Bayer and team)
- Celery maintainers and community
- Production implementations (Apache Superset, various Stack Overflow answers)
- Community blog posts (Ryan Zheng, Yang Wang, David Caron)

Special thanks to the open-source community for documenting these complex integration challenges.
