# Prefect Architecture Summary: GRIB2 ETL Pipeline

## Executive Summary

Migrating from Celery to Prefect for a surf forecast ETL pipeline that downloads GRIB2 files, performs nearest-neighbor searches, transforms data, and stores to Redis. Key architectural decisions center around resource management, concurrency control, and proper async patterns.

---

## Core Concepts & Issues Resolved

### 1. **Prefect's Execution Model**

**Key Insight**: Prefect workers spawn a **new subprocess for each flow run**.

```
Worker Process (--limit 10)
├─> Flow Run 1 (subprocess)
├─> Flow Run 2 (subprocess)
├─> Flow Run 3 (subprocess)
└─> ... up to 10 concurrent subprocesses
```

**Implications**:
- Each flow run gets a fresh Python interpreter
- No shared state between flow runs by default
- Resource pools must be initialized per flow run
- Global variables reset each subprocess

**Solution**: Initialize expensive resources (HTTP clients, DB pools, Redis connections) **once per flow run** and pass them to child flows/tasks.

---

### 2. **Resource Pool Management Strategy**

**❌ What Doesn't Work**:
- Prefect Blocks (config storage, not resource lifecycle management)
- Global singletons (reset per subprocess)
- Worker-level resource pools (no mechanism for this in Prefect)

**✅ Recommended Pattern**: Context-managed resource container passed as flow parameters

```python
@dataclass
class ForecastResourceManagers:
    http: AsyncHTTPManager
    redis: AsyncRedisManager
    db: AsyncDatabaseManager
    
    @classmethod
    async def create(cls) -> "ForecastResourceManagers":
        # Initialize all pools once
        ...
    
    async def close(self):
        # Clean up all resources
        ...

@asynccontextmanager
async def forecast_resources():
    managers = await ForecastResourceManagers.create()
    try:
        yield managers
    finally:
        await managers.close()
```

**Usage**:
```python
@flow
async def orchestration_flow():
    async with forecast_resources() as managers:
        # Pass managers to all child flows/tasks
        await process_region_forecast(region, managers)
```

**Why This Works**:
- Resources scoped to flow run lifecycle
- Proper cleanup guaranteed
- Shared across all tasks in the flow run
- No globals needed
- Prefect-native (works with subprocess model)

---

### 3. **Concurrency Control Hierarchy**

Prefect has **multiple levels** of concurrency control:

```
┌─────────────────────────────────────────────────┐
│ Global Concurrency Limits (cross-worker)       │
│ - Named slots: "postgres-pool", "httpx-pool"   │
│ - Enforce resource limits across ALL workers   │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Work Pool Concurrency (pool-wide)              │
│ - Limits concurrent flow runs across workers   │
│ - Set via: prefect work-pool update            │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Worker Concurrency (per worker)                │
│ - --limit flag on worker start                 │
│ - Max concurrent subprocesses per worker       │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Task Runner Concurrency (within flow)          │
│ - ThreadPoolTaskRunner(max_workers=5)          │
│ - Controls task parallelism inside flow        │
└─────────────────────────────────────────────────┘
```

**For Your Use Case**: 
- **Worker limit**: `--limit 10` (10 concurrent flow runs)
- **Task runner**: `ThreadPoolTaskRunner(max_workers=5)` (5 regions processed concurrently)
- **Global limits**: Optional, if you want to enforce hard resource caps

**Do NOT use** Global Concurrency Limits for your case - you're managing pools directly.

---

### 4. **Async vs Sync: Clear Winner**

**Decision**: Go **fully async** with Prefect.

| Aspect | Celery (Old) | Prefect (New) |
|--------|--------------|---------------|
| Async Support | Poor (event loop conflicts) | Native, excellent |
| Resource Model | Sync managers required | Async managers work perfectly |
| I/O Operations | Blocking | True async concurrency |
| Code Complexity | Sync/async splits | Clean, consistent async |

**Migration**:
- Use `AsyncHTTPManager`, `AsyncRedisManager`, `AsyncDatabaseManager`
- Repository becomes `AsyncSurfSpotRepository` with `AsyncSession`
- Provider methods are `async def`
- Remove all sync variants

**Note**: xarray/cfgrib operations are CPU-bound and remain blocking, but everything else (HTTP downloads, DB queries, Redis writes) gets true async benefits.

---

### 5. **Logging Strategy**

**Question**: Should you use Prefect's logger or standard Python logging?

**Answer**: Use **Prefect's logger** for all code that runs in Prefect context.

**Why**:
- Automatic flow/task context (run IDs, task names)
- Integrated with Prefect UI (searchable, filterable)
- Structured logging support
- Consistent formatting

**Implementation**:

```python
from prefect import get_run_logger

# ❌ Old way (standard logging)
logger = logging.getLogger(__name__)
logger.info("Downloading file")

# ✅ New way (Prefect logger)
@task
async def download_forecast_file(...):
    logger = get_run_logger()
    logger.info(
        "Downloading GRIB2 file",
        extra={
            "region": region.value,
            "file": filename,
            "url": url
        }
    )
```

**Migration Path**:
1. Replace `logging.getLogger(__name__)` with `get_run_logger()` inside tasks/flows
2. Keep standard logging for non-Prefect code (if any)
3. Prefect automatically captures standard logging too, but native logger is better

**Exception**: If provider classes are used outside Prefect (CLI tools, tests), use standard logging there and let Prefect capture it.

---

### 6. **Architectural Patterns**

**Pattern 1: Orchestrator → Dispatcher → Worker**

```python
@flow(name="orchestrator")
async def orchestrate_nwps_forecasts():
    """Top-level: initialize resources, dispatch regions"""
    async with forecast_resources() as managers:
        for region in enabled_regions:
            await process_region_forecast(region, managers)

@flow(name="region-processor")
async def process_region_forecast(region, managers):
    """Mid-level: coordinate regional processing"""
    run_data = await check_latest_run(region, managers)
    file_path = await download_forecast_file(...)
    forecasts = await extract_and_process(...)
    await store_to_redis(...)

@task
async def download_forecast_file(...):
    """Leaf-level: atomic operations"""
    ...
```

**Pattern 2: Provider Composition**

```python
# Provider classes are NOT flows/tasks themselves
# They're domain objects used WITHIN tasks

@task
async def extract_forecasts(region, file_path, managers):
    config = get_nomads_config(region, NOMADSModel.NWPS)
    
    async with managers.db.explicit_commit_session() as session:
        repo = AsyncSurfSpotRepository(session)
        provider = NOMADSProvider(config, managers.http, repo)
        
        # Provider does domain logic, not Prefect orchestration
        return await provider.extract_forecasts(file_path)
```

**Key Principle**: 
- **Flows/Tasks** = Orchestration layer (Prefect concepts)
- **Providers/Repositories** = Domain layer (business logic)
- Keep them separate for testability and clarity

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Orchestration Flow (orchestrate_nwps_forecasts)        │
│ - Initialize ForecastResourceManagers                  │
│ - Get enabled regions                                   │
│ - Fan out to region processors                          │
└─────────────────────────────────────────────────────────┘
                         ↓ (for each region)
┌─────────────────────────────────────────────────────────┐
│ Regional Processor Flow (process_region_forecast)      │
│ - Check availability (task)                             │
│ - Download GRIB2 (task)                                 │
│ - Extract forecasts (task)                              │
│ - Store to Redis (task)                                 │
└─────────────────────────────────────────────────────────┘
                         ↓ (within tasks)
┌─────────────────────────────────────────────────────────┐
│ Domain Layer (NOMADSProvider, Repository)              │
│ - Uses managers.http, managers.db, managers.redis      │
│ - Pure domain logic, no Prefect awareness              │
│ - Uses Prefect logger via get_run_logger()             │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Checklist

### Phase 1: Core Migration
- [ ] Create `ForecastResourceManagers` with async managers
- [ ] Convert repository to `AsyncSurfSpotRepository`
- [ ] Update `NOMADSProvider` to accept async managers
- [ ] Update `NOMADSAvailabilityChecker` for async

### Phase 2: Prefect Integration
- [ ] Create orchestration flow (`orchestrate_nwps_forecasts`)
- [ ] Create regional processor flow (`process_region_forecast`)
- [ ] Extract tasks: `check_latest_run`, `download_forecast_file`, etc.
- [ ] Add retry strategies per task

### Phase 3: Logging & Observability
- [ ] Replace `logging.getLogger()` with `get_run_logger()` in tasks
- [ ] Add structured logging with `extra={}` dicts
- [ ] Test log visibility in Prefect UI

### Phase 4: Deployment
- [ ] Create deployment with schedule (3x daily for HFO)
- [ ] Configure work pool and worker
- [ ] Set worker concurrency limit (e.g., `--limit 10`)
- [ ] Test end-to-end execution

---

## Key Takeaways

1. **Resource Management**: Initialize once per flow run, pass as parameters
2. **Concurrency**: Use worker `--limit` and `ThreadPoolTaskRunner`, not Global Concurrency Limits
3. **Async**: Go fully async - Prefect handles it beautifully
4. **Logging**: Use `get_run_logger()` in all tasks/flows
5. **Separation**: Flows/tasks for orchestration, providers for domain logic
6. **Context Managers**: Use `async with` for resource lifecycle

---

## Example Flow Structure

```python
# File: services/forecast/flows/orchestration.py

from prefect import flow, task, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner

@task(name="check-availability", retries=2)
async def check_latest_run(region, managers):
    logger = get_run_logger()
    logger.info(f"Checking availability for {region.value}")
    ...

@task(name="download-grib2", retries=3)
async def download_forecast_file(region, analysis_time, forecast_date, managers):
    logger = get_run_logger()
    logger.info(f"Downloading GRIB2 for {region.value}")
    ...

@flow(name="process-region-forecast")
async def process_region_forecast(region, managers):
    logger = get_run_logger()
    logger.info(f"Processing {region.value}")
    
    run_data = await check_latest_run(region, managers)
    if not run_data:
        return {"status": "no_data"}
    
    forecast_date, analysis_time = run_data
    file_path = await download_forecast_file(region, analysis_time, forecast_date, managers)
    forecasts = await extract_and_process(region, file_path, managers)
    await store_to_redis(forecasts, managers)
    
    return {"status": "success", "spots": len(forecasts)}

@flow(
    name="nwps-orchestration",
    task_runner=ThreadPoolTaskRunner(max_workers=5)
)
async def orchestrate_nwps_forecasts():
    logger = get_run_logger()
    
    async with forecast_resources() as managers:
        logger.info("Starting NWPS orchestration")
        
        enabled_regions = get_enabled_regions_for_model(NOMADSModel.NWPS)
        
        results = []
        for region in enabled_regions:
            result = await process_region_forecast(region, managers)
            results.append(result)
        
        logger.info(f"Completed {len(results)} regions")
        return results
```

---

## Questions Resolved

| Question | Answer |
|----------|--------|
| How to handle resource pools in Prefect? | Initialize per flow run, pass as parameters |
| Should I use Blocks for connection pools? | No - Blocks are for config, not resource lifecycle |
| Can I use global singletons? | No - they reset per subprocess |
| What about Global Concurrency Limits? | Not needed - you manage pools directly |
| Async or sync? | Fully async - Prefect handles it natively |
| Which logger to use? | `get_run_logger()` in tasks/flows |
| How to structure flows vs domain logic? | Flows/tasks = orchestration, providers = domain |
| How many workers do I need? | One worker is fine with `--limit` for concurrency |

---

## Further Reading

- [Prefect Work Pools](https://docs.prefect.io/v3/concepts/work-pools)
- [Prefect Task Runners](https://docs.prefect.io/v3/concepts/task-runners)
- [Prefect Logging](https://docs.prefect.io/v3/how-to-guides/workflows/add-logging)
- [Async Flows](https://docs.prefect.io/v3/concepts/flows)
