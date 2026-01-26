# Celery → Prefect Migration Analysis

> **Date:** 2026-01-18
> **Scope:** Comprehensive analysis of migrating forecast ETL from Celery to Prefect

---

## Table of Contents

1. [Current Architecture Summary](#1-current-architecture-summary)
2. [Prefect Architecture Changes Required](#2-prefect-architecture-changes-required)
3. [Best Execution Strategy for Multi-Provider Forecasts](#3-best-execution-strategy-for-multi-provider-forecasts)
4. [Migration Difficulty Assessment](#4-migration-difficulty-assessment)
5. [Redis as Final Load Target](#5-redis-as-final-load-target)
6. [PostgreSQL/PostGIS with Prefect](#6-postgresqlpostgis-with-prefect)
7. [Architecture Guidelines & Refactoring Considerations](#7-architecture-guidelines--refactoring-considerations)
8. [Migration Checklist](#8-migration-checklist)

---

## Key Insight: Celery vs Prefect Paradigm

**Celery** is a *distributed task queue* (fire-and-forget tasks with retries), while **Prefect** is a *workflow orchestration platform* (DAG-based flows with observability). The current architecture maps well to Prefect because tasks already have clear parent→child relationships (e.g., `fetch_all_nwps_forecasts` → `fetch_nwps(region)`).

---

## 1. Current Architecture Summary

The ETL pipeline is well-structured:

| Component | Current Implementation | Key Files |
|-----------|----------------------|-----------|
| **Scheduler** | Celery Beat (crontab) | `workers/celery_app.py` |
| **Task Queue** | Celery + Redis broker | `core/configs/celery_config.py` |
| **Workers** | Prefork pool (concurrency=2) | `workers/tasks/nomads.py`, `pacioos.py` |
| **Orchestration** | Celery `group()` for fan-out | Parent tasks spawn children |
| **State** | Redis (last_run_id tracking) | Keys: `forecast:nomads:nwps:{region}:last_run` |
| **Load Target** | Redis with TTL | 14h NWPS, 8d PacIOOS |

**Current Flow Pattern:**

```
Beat Schedule → Parent Task → group([child_tasks]) → Provider Extract → Transform → Redis Load
```

---

## 2. Prefect Architecture Changes Required

### 2.1 Conceptual Mapping

| Celery Concept | Prefect Equivalent | Notes |
|----------------|-------------------|-------|
| `@shared_task` | `@task` | Prefect tasks are async-native |
| `@app.task(bind=True)` | `@task(retries=3)` | Built-in retry with backoff |
| Celery Beat | Prefect Deployments + Schedules | YAML or Python-based |
| `group()` | `task.map()` or `async gather` | Native concurrent execution |
| Redis broker | **Not needed** | Prefect uses its own orchestration |
| Flower | Prefect UI | Much richer observability |
| `max_retries` + `countdown` | `@task(retries=3, retry_delay_seconds=[60, 300, 900])` | Exponential backoff built-in |

### 2.2 Structural Changes

**Before (Celery):**

```
backend/
├── workers/
│   ├── celery_app.py          # DELETE
│   ├── signals.py             # ADAPT → Prefect hooks
│   └── tasks/
│       ├── nomads.py          # REFACTOR → flows/nomads.py
│       └── pacioos.py         # REFACTOR → flows/pacioos.py
```

**After (Prefect):**

```
backend/
├── flows/
│   ├── __init__.py
│   ├── nomads.py              # @flow + @task definitions
│   ├── pacioos.py             # @flow + @task definitions
│   └── shared/
│       └── redis_loader.py    # Shared load task
├── deployments/
│   └── prefect.yaml           # Schedule definitions
```

---

## 3. Best Execution Strategy for Multi-Provider Forecasts

### Key Insight: Async vs Distributed for I/O-Bound ETL

Forecast providers are heavily I/O-bound (downloading GRIB2/NetCDF files, HTTP requests). For I/O-bound workloads, **async concurrency within a single worker** often outperforms distributed workers because you avoid serialization overhead and network hops between workers.

### Recommended: Hybrid Async + Task-Level Parallelism

```python
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner
import asyncio

@task(retries=3, retry_delay_seconds=[300, 600, 3600])
async def fetch_nwps_region(region: Region) -> dict:
    """Single region extraction - I/O bound, runs async."""
    async with httpx.AsyncClient() as client:
        # Check availability, download, extract...
        pass

@flow(task_runner=ConcurrentTaskRunner())
async def fetch_all_nwps_forecasts():
    """Parent flow - fans out to all regions concurrently."""
    enabled_regions = get_enabled_regions()

    # Option A: task.map() - Prefect manages concurrency
    results = await fetch_nwps_region.map(enabled_regions)

    # Option B: asyncio.gather - explicit async control
    results = await asyncio.gather(
        *[fetch_nwps_region(r) for r in enabled_regions]
    )
    return results
```

### Strategy Comparison

| Strategy | Pros | Cons | Best For |
|----------|------|------|----------|
| **Distributed Workers** | True parallelism, fault isolation | Serialization overhead, complex state | CPU-bound, long-running |
| **Async (ConcurrentTaskRunner)** | Low overhead, shared connections | Single-process limits | I/O-bound (this use case) |
| **Hybrid** | Best of both | Slightly complex | Multi-provider, mixed workloads |

**Workload Characteristics:**

- Downloads: 20-30MB GRIB2 files (I/O bound ✓)
- Transforms: xarray/numpy operations (CPU burst, but fast)
- Regions: Currently small (Maui), scales to ~10 regions

**Recommendation:** Start with `ConcurrentTaskRunner` (async) for each provider flow. Only add distributed workers (Dask/Ray) if you scale to 50+ regions or add CPU-intensive post-processing.

---

## 4. Migration Difficulty Assessment

### 4.1 Complexity Breakdown

| Component | Difficulty | Effort | Notes |
|-----------|-----------|--------|-------|
| Task definitions | 🟢 Low | 2-3 hours | Direct mapping to `@task` |
| Retry logic | 🟢 Low | 1 hour | Prefect has better built-in support |
| Beat schedules → Deployments | 🟡 Medium | 2-3 hours | Different paradigm (YAML/Python) |
| Redis Load (unchanged) | 🟢 Low | 0 hours | No changes needed |
| Docker compose | 🟡 Medium | 2-3 hours | Replace worker/beat/flower services |
| Celery signals → Prefect hooks | 🟡 Medium | 1-2 hours | Different lifecycle model |
| Testing | 🟡 Medium | 3-4 hours | Prefect has good testing utilities |
| **Total** | | **~12-16 hours** | For experienced developer |

### 4.2 What Gets Easier

```python
# Current Celery retry (complex)
@shared_task(bind=True, max_retries=3)
def fetch_nwps(self, region_str: str):
    try:
        # ... work
    except NoNewRunAvailable:
        raise self.retry(countdown=3600, max_retries=3)
    except NetworkError:
        raise self.retry(countdown=300, max_retries=3)

# Prefect equivalent (cleaner)
@task(
    retries=3,
    retry_delay_seconds=[300, 600, 3600],
    retry_condition_fn=lambda task, state: should_retry(state.result())
)
async def fetch_nwps(region: Region):
    # ... work (exceptions auto-retry)
```

### 4.3 What Gets Harder

- **Learning curve**: Prefect's deployment model (work pools, workers, deployments)
- **Local dev**: Need Prefect server running (or use Prefect Cloud)
- **State inspection**: Different debugging patterns than Celery/Flower

---

## 5. Redis as Final Load Target

**Zero changes required to the Redis loading pattern.**

```python
# Current pattern (keeps working exactly as-is)
@task
async def load_forecasts_to_redis(forecasts: dict[str, ProviderForecast], config: Config):
    """Load step - unchanged from Celery implementation."""
    async with redis_manager.client.pipeline() as pipe:
        for spot_id, forecast in forecasts.items():
            key = f"forecast:{config.provider}:{config.model}:{config.region}:{spot_id}"
            pipe.setex(key, config.ttl, forecast.to_redis_json())
        pipe.set(f"forecast:{config.provider}:{config.model}:{config.region}:last_run", run_id)
        await pipe.execute()
```

### Key Insight

**Prefect Doesn't Care About Your Load Target**: Unlike Celery (which uses Redis as broker AND can use it for results), Prefect completely separates orchestration state from application data. The Redis caching layer is orthogonal to Prefect—it's just Python code inside a task.

---

## 6. PostgreSQL/PostGIS with Prefect

### 6.1 Using Existing Database

**Yes, you can use the existing PostgreSQL instance**, but with important considerations:

| Use Case | Recommendation |
|----------|---------------|
| **Prefect Server metadata** | Separate database (or separate schema) |
| **Application data** | Keep existing `nana_nalu` database |
| **Shared instance** | ✅ Works fine with schema isolation |

### 6.2 Configuration Options

**Option A: Same Instance, Different Database (Recommended)**

```yaml
# docker-compose.yml
services:
  prefect-server:
    image: prefecthq/prefect:2-python3.12
    environment:
      PREFECT_API_DATABASE_CONNECTION_URL: "postgresql+asyncpg://user:pass@db:5432/prefect"
    depends_on:
      - db
```

**Option B: Same Database, Different Schema**

```python
# prefect config
PREFECT_API_DATABASE_CONNECTION_URL="postgresql+asyncpg://user:pass@db:5432/nana_nalu?options=-c%20search_path%3Dprefect"
```

**Option C: Prefect Cloud (Simplest)**

- No database management needed
- Free tier available for small projects
- Prefect manages all orchestration state

### 6.3 PostGIS Compatibility

PostGIS queries in `SyncSurfSpotRepository.get_all_in_grid()` work unchanged:

```python
@task
async def extract_spots_in_grid(config: NWPSConfig) -> list[SurfSpot]:
    """Uses existing repository - PostGIS queries work as before."""
    async with get_async_db_session() as session:
        repo = AsyncSurfSpotRepository(session)
        return await repo.get_all_in_grid(
            config.lat_min, config.lat_max,
            config.long_min, config.long_max
        )
```

---

## 7. Architecture Guidelines & Refactoring Considerations

### 7.1 Recommended Flow Structure

```
flows/
├── nomads/
│   ├── __init__.py
│   ├── flow.py           # Main NWPS flow
│   └── tasks.py          # check_availability, download, extract, load
├── pacioos/
│   ├── __init__.py
│   ├── flow.py           # Main Tide/SWAN/WRF flows
│   └── tasks.py
└── common/
    ├── redis_tasks.py    # Shared load_to_redis task
    └── notifications.py  # Alert on failure (optional)
```

### 7.2 Flow Pattern for This Use Case

```python
# flows/nomads/flow.py
from prefect import flow
from prefect.deployments import DeploymentImage

@flow(
    name="nomads-nwps-forecast",
    description="Fetch NWPS forecasts for all enabled regions",
    retries=0,  # Let tasks handle retries
    log_prints=True
)
async def fetch_all_nwps_forecasts():
    enabled_regions = get_enabled_regions()

    # Fan-out: check availability for all regions
    availability = await check_availability.map(enabled_regions)

    # Filter to regions with new data
    regions_to_fetch = [
        r for r, avail in zip(enabled_regions, availability)
        if avail.has_new_run
    ]

    # Fan-out: fetch and load each region
    results = await fetch_and_load_region.map(regions_to_fetch)

    return {"processed": len(results), "regions": [r.name for r in regions_to_fetch]}
```

### 7.3 Deployment Configuration

```yaml
# deployments/prefect.yaml
deployments:
  - name: nomads-nwps-morning
    entrypoint: flows/nomads/flow.py:fetch_all_nwps_forecasts
    work_pool:
      name: forecast-pool
    schedule:
      cron: "0 10 * * *"  # 10:00 UTC
      timezone: "UTC"

  - name: nomads-nwps-evening
    entrypoint: flows/nomads/flow.py:fetch_all_nwps_forecasts
    work_pool:
      name: forecast-pool
    schedule:
      cron: "0 21 * * *"  # 21:00 UTC
      timezone: "UTC"

  - name: pacioos-tide-weekly
    entrypoint: flows/pacioos/flow.py:fetch_all_tide_forecasts
    work_pool:
      name: forecast-pool
    schedule:
      cron: "0 6 * * 0"   # Sundays 6:00 UTC
      timezone: "UTC"
```

### 7.4 Docker Compose Changes

```yaml
# docker-compose.yml changes
services:
  # REMOVE these:
  # worker: ...
  # beat: ...
  # flower: ...

  # ADD these:
  prefect-server:
    image: prefecthq/prefect:2-python3.12
    command: prefect server start --host 0.0.0.0
    environment:
      PREFECT_API_DATABASE_CONNECTION_URL: "postgresql+asyncpg://..."
    ports:
      - "4200:4200"
    depends_on:
      - db

  prefect-worker:
    build:
      context: ./backend
      target: worker  # Reuse worker Dockerfile
    command: prefect worker start --pool forecast-pool
    environment:
      PREFECT_API_URL: "http://prefect-server:4200/api"
    depends_on:
      - prefect-server
      - redis
      - db
```

### 7.5 Key Refactoring Considerations

| Current Pattern | Prefect Adaptation |
|----------------|-------------------|
| `SyncDatabaseManager` | Switch to `AsyncDatabaseManager` (Prefect is async-native) |
| `SyncRedisManager` | Switch to `AsyncRedisManager` |
| `SyncHTTPManager` | Switch to `AsyncHTTPManager` |
| `worker_process_init` signal | Use Prefect hooks or flow-level setup |
| `task_routes` (queue routing) | Work pools with tags |
| `max_tasks_per_child=100` | Not needed (no prefork) |

### 7.6 Preserving Intelligent Polling

The availability checking pattern maps directly:

```python
@task(
    retries=3,
    retry_delay_seconds=[3600, 3600, 3600],  # 1-hour intervals
    retry_condition_fn=lambda _, state: isinstance(state.result(), NoNewRunAvailable)
)
async def check_and_fetch_nwps(region: Region):
    """Maps current intelligent retry pattern."""
    availability = await check_nomads_availability(region)

    if not availability.has_new_run:
        raise NoNewRunAvailable()  # Triggers retry

    if availability.is_too_old:
        return {"status": "skipped", "reason": "data too old"}

    return await fetch_and_load(region, availability)
```

---

## 8. Migration Checklist

### Phase 1: Setup (1-2 hours)

- [ ] Add prefect to pyproject.toml
- [ ] Create flows/ directory structure
- [ ] Set up local Prefect server (or Prefect Cloud)

### Phase 2: Convert Tasks (3-4 hours)

- [ ] Convert nomads.py tasks to async @task decorators
- [ ] Convert pacioos.py tasks to async @task decorators
- [ ] Update to use AsyncDatabaseManager/AsyncRedisManager

### Phase 3: Create Flows (2-3 hours)

- [ ] Create NWPS parent flow with fan-out
- [ ] Create PacIOOS parent flow with fan-out
- [ ] Test locally with `python flows/nomads/flow.py`

### Phase 4: Deployments (2-3 hours)

- [ ] Create prefect.yaml with schedules
- [ ] Set up work pool
- [ ] Deploy with `prefect deploy --all`

### Phase 5: Infrastructure (2-3 hours)

- [ ] Update docker-compose.yml
- [ ] Remove Celery services
- [ ] Add Prefect server + worker services
- [ ] Test full stack locally

### Phase 6: Cutover

- [ ] Stop Celery workers
- [ ] Start Prefect workers
- [ ] Verify forecasts flowing to Redis

---

## When Prefect Shines Over Celery for This Use Case

1. **Observability** - Prefect UI shows flow DAGs, task dependencies, and run history (better than Flower)
2. **Dynamic Workflows** - Availability checking creates conditional paths; Prefect handles this natively
3. **Async Native** - Providers are I/O-bound; Prefect's async-first model is a natural fit
4. **Caching** - `@task(cache_key_fn=...)` can prevent re-fetching unchanged data (useful for `last_run_id` pattern)

---

## References

- [Prefect 2.x Documentation](https://docs.prefect.io/)
- [Prefect Task Runners](https://docs.prefect.io/concepts/task-runners/)
- [Prefect Deployments](https://docs.prefect.io/concepts/deployments/)
- [Migrating from Celery](https://docs.prefect.io/migration/celery/)
