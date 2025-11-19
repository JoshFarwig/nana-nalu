# Celery + Async Code Quick Start

## TL;DR

**Problem**: Want to share async code (DB, Redis, repositories) between FastAPI and Celery.

**Solution**: Keep everything async, wrap Celery tasks with `asyncio.run()`, use `worker_process_init` signal.

---

## Quick Setup

### 1. Update Database Manager

```python
# core/database.py
from threading import local

# Add process-local storage
process_local = local()

# Keep your existing AsyncDatabaseManager class as-is

# Add these new functions:
async def create_engine_for_worker(settings: DatabaseConfig):
    """Create engine for Celery worker (called from worker_process_init)."""
    engine = create_async_engine(
        settings.get_async_url(),
        pool_size=2,  # Small pool for workers
        max_overflow=3,
        pool_pre_ping=True,
    )
    process_local.engine = engine
    process_local.session_factory = async_sessionmaker(engine, ...)
    return engine

async def dispose_engine():
    """Dispose worker engine (called from worker_process_shutdown)."""
    if hasattr(process_local, 'engine'):
        await process_local.engine.dispose()
        del process_local.engine
        del process_local.session_factory

def get_session_factory():
    """Get session factory (works for both FastAPI and Celery)."""
    # Celery worker: use process-local
    if hasattr(process_local, 'session_factory'):
        return process_local.session_factory
    # FastAPI: use default
    return default_session_factory

# Update your get_session() to use get_session_factory():
@asynccontextmanager
async def get_session():
    factory = get_session_factory()  # ← Changed
    async with factory() as session:
        # ... rest stays same
```

### 2. Create Worker Signals

```python
# workers/signals.py
from celery.signals import worker_process_init, worker_process_shutdown
from core.database import create_engine_for_worker, dispose_engine
from core.configs import get_settings
import asyncio

@worker_process_init.connect
def init_worker(**kwargs):
    """Runs in EACH worker process after fork."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    settings = get_settings()
    loop.run_until_complete(create_engine_for_worker(settings.db))

@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    """Clean up worker resources."""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(dispose_engine())
```

### 3. Create Celery App

```python
# workers/app.py
from celery import Celery
from core.configs import get_settings

settings = get_settings()

app = Celery(
    'nana_nalu',
    broker=settings.redis.broker_url.get_secret_value(),
    backend=settings.redis.broker_url.get_secret_value(),
)

app.conf.update(
    worker_pool='prefork',
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)

# Import signals (IMPORTANT!)
from workers import signals  # noqa

# Import tasks
from workers.tasks import forecast  # noqa
```

### 4. Write Tasks (Sync Wrapper Pattern)

```python
# workers/tasks/forecast.py
from celery import shared_task
from core.database import get_session
from repositories.surf_spot_repository import SurfSpotRepository
import asyncio

@shared_task
def fetch_nwps_forecasts(region: str):
    """Sync wrapper for async implementation."""
    return asyncio.run(_fetch_nwps_async(region))

async def _fetch_nwps_async(region: str):
    """Async implementation - reuses all your async code!"""
    async with get_session() as session:
        # Your async repository works!
        repo = SurfSpotRepository(session)
        spots = await repo.get_all_in_grid(...)

        # Your async provider works!
        provider = NWPSProvider(...)
        file_path = await provider.download_file(...)
        forecasts = await provider.extract_forecasts(file_path)

        return forecasts
```

### 5. Run Celery

```bash
# Development
celery -A workers.app worker --loglevel=info --concurrency=2

# Production
celery -A workers.app worker --loglevel=info --concurrency=4
```

---

## The Pattern

```
┌─────────────────────────────┐
│ @shared_task                │  ← Sync function (Celery requirement)
│ def my_task():              │
│   return asyncio.run(impl)  │  ← Wraps async with asyncio.run()
└─────────────────────────────┘
              ↓
┌─────────────────────────────┐
│ async def impl():           │  ← Async implementation
│   async with get_session(): │  ← Uses process-local engine
│     await repo.method()     │  ← Reuses async repos
└─────────────────────────────┘
```

---

## Common Questions

### Q: Do I need separate sync repositories?

**A: NO!** Reuse your async repositories. Just wrap task with `asyncio.run()`.

### Q: Is there overhead from creating engine per task?

**A: NO!** With `worker_process_init`, engine is created ONCE per worker process, not per task.

### Q: Can I use asyncio.to_thread() in my providers?

**A: YES!** Keep your NWPS provider exactly as-is with `asyncio.to_thread()`. It helps when:
- Multiple I/O operations run concurrently
- CPU work doesn't block the event loop

### Q: Should I gather providers in one task?

**A: NO!** With prefork pool, use separate tasks:
```python
@shared_task
def fetch_nwps():
    return asyncio.run(_fetch_nwps_async())

@shared_task
def fetch_gfs():
    return asyncio.run(_fetch_gfs_async())

# Celery runs them in parallel on different workers
```

### Q: What about solo pool?

**A: Works the same!** The pattern works for both solo and prefork pools.

---

## Key Files to Create/Modify

**Create**:
- `workers/__init__.py`
- `workers/app.py` - Celery app config
- `workers/signals.py` - worker_process_init/shutdown
- `workers/tasks/__init__.py`
- `workers/tasks/forecast.py` - Your tasks

**Modify**:
- `core/database.py` - Add `create_engine_for_worker()`, `dispose_engine()`, `get_session_factory()`
- `core/configs/celery_config.py` - Update to use prefork

**Don't Modify**:
- Repositories (keep async)
- Providers (keep async)
- Services (keep async)

---

## What NOT to Do

### ❌ Don't create WorkerState singleton
```python
# ❌ WRONG
class WorkerState:
    loop = asyncio.new_event_loop()
    db_manager = AsyncDatabaseManager(...)
```

### ❌ Don't use worker_init signal
```python
# ❌ WRONG (runs in parent process)
@signals.worker_init.connect
def init(**kwargs):
    ...

# ✅ CORRECT (runs in each child)
@signals.worker_process_init.connect
def init(**kwargs):
    ...
```

### ❌ Don't create engine at import time
```python
# ❌ WRONG (created before fork)
db_manager = AsyncDatabaseManager(settings)

# ✅ CORRECT (created after fork in signal)
@worker_process_init.connect
def init(**kwargs):
    asyncio.run(create_engine_for_worker(settings))
```

---

## Debugging

### Check worker is using process-local engine

```python
@shared_task
def debug_task():
    def _debug():
        from threading import local as thread_local
        from core.database import process_local

        has_engine = hasattr(process_local, 'engine')
        pid = os.getpid()

        return {
            'has_process_local_engine': has_engine,
            'worker_pid': pid,
        }

    return asyncio.run(_debug())
```

### Enable SQL logging

```python
# In create_engine_for_worker()
engine = create_async_engine(
    url,
    echo=True,  # ← Add this
    pool_size=2,
)
```

---

## Summary

**What you're doing**:
- Keeping all async code (repos, providers, services)
- Using `asyncio.run()` wrapper in Celery tasks
- Using `worker_process_init` to create engine per worker process

**What you're NOT doing**:
- Creating singleton WorkerState
- Duplicating code as sync versions
- Creating engine per task (only per worker process)

**Benefits**:
- ✅ 100% code reuse between FastAPI and Celery
- ✅ No duplication
- ✅ Proper process isolation
- ✅ Production-proven pattern
