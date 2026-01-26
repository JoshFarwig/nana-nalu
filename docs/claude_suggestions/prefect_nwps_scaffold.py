"""
Prefect scaffolding for NWPS ETL pipeline.

This demonstrates Prefect patterns for the existing Celery-based NOMADS NWPS workflow.
Key architectural decisions are explained in comments.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from prefect import flow, task
from prefect.tasks import task_input_hash
from prefect.blocks.system import Secret  # For API keys, connection strings

# Your existing imports
from services.forecast.providers.nomads.provider import NOMADSProvider
from services.forecast.providers.nomads.availability import NOMADSAvailabilityChecker
from services.forecast.forecast_schema import ProviderForecast
from utils.region import Region


# ============================================================================
# TASK vs FLOW DISTINCTION
# ============================================================================
#
# TASKS: Atomic units of work that can be retried, cached, and monitored
#        - Should be idempotent (same input = same output)
#        - Fine-grained (download, transform, load separately)
#        - Can be cached to avoid re-computation
#
# FLOWS: Orchestration layer that chains tasks into a DAG
#        - Defines dependencies between tasks
#        - Handles overall workflow logic
#        - Can call other flows (subflows)
# ============================================================================


# ============================================================================
# DEPENDENCY MANAGEMENT PATTERN
# ============================================================================
#
# Option 1: Prefect Blocks (recommended for production)
#   - Define reusable connection configs in Prefect Cloud UI
#   - Reference by name: redis_block = RedisBlock.load("my-redis")
#   - Good for credentials, connection strings
#
# Option 2: Dependency Injection (shown here, simpler for migration)
#   - Pass managers/clients as task parameters
#   - Instantiate once in flow, reuse across tasks
#   - Easier to test, familiar pattern
#
# Option 3: Context Managers (for resources that need cleanup)
#   - Use within tasks for file handles, connections
#   - Prefect handles cleanup on failure
# ============================================================================


# ============================================================================
# TASKS (Granular Operations)
# ============================================================================

@task(
    name="check-nwps-availability",
    retries=3,
    retry_delay_seconds=300,  # 5 min for network issues
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(minutes=30),  # Cache availability checks
)
def check_availability(
    region: str,
    last_run_time: datetime | None,
) -> tuple[datetime, str] | None:
    """
    Check if new NWPS run is available.

    Returns:
        (analysis_time, download_url) if available, None otherwise

    Cache Strategy:
        - Caches based on inputs (region + last_run_time)
        - Prevents redundant polling within 30 min window
        - Prefect auto-invalidates cache when inputs change
    """
    checker = NOMADSAvailabilityChecker(
        wfo="hfo",
        region=region,
        last_run_time=last_run_time,
    )

    result = checker.find_latest_run()
    if not result:
        return None

    analysis_time, url = result

    # Age validation (your current logic)
    age_hours = (datetime.utcnow() - analysis_time).total_seconds() / 3600
    if age_hours > 18:
        return None

    return analysis_time, url


@task(
    name="download-grib-file",
    retries=3,
    retry_delay_seconds=300,
    timeout_seconds=600,  # 10 min max for download
)
def download_grib_file(url: str, output_path: Path) -> Path:
    """
    Download GRIB2 file from NOMADS.

    Dependency Injection:
        - Could accept http_client as parameter
        - Or instantiate httpx client here (lightweight)
        - Prefect handles cleanup on task completion

    Async Note:
        - Could be `async def download_grib_file(...)`
        - Prefect 2.x fully supports async tasks
        - Just await the httpx async client
    """
    import httpx

    # Use sync client for now (matches your current pattern)
    # TODO: Could use async httpx for better concurrency
    with httpx.stream("GET", url, timeout=600) as response:
        response.raise_for_status()

        with output_path.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=512 * 1024):
                f.write(chunk)

    return output_path


@task(
    name="extract-nwps-forecasts",
    retries=2,
    retry_delay_seconds=60,
)
def extract_forecasts(
    file_path: Path,
    region: Region,
    db_manager: Any,  # Your SyncDatabaseManager
) -> dict[int, ProviderForecast]:
    """
    Extract forecasts from GRIB2 file for all spots in region.

    Parallelization Opportunity:
        - xarray operations are currently CPU-bound
        - Could use DaskTaskRunner in flow for parallel spot processing
        - Or use dask-backed xarray arrays for lazy computation

    Dependency Pattern:
        - db_manager passed from flow (instantiated once)
        - Avoids creating connection pool per task
        - Could also use Prefect SQLAlchemyBlock
    """
    provider = NOMADSProvider(
        wfo="hfo",
        region=region.value,
        model="nwps",
        db_manager=db_manager,
    )

    # This is your current extraction logic
    # NOTE: Could be optimized with Dask for large grids
    forecasts = provider.extract_forecasts(file_path)

    return forecasts


@task(
    name="load-forecasts-to-redis",
    retries=3,
    retry_delay_seconds=60,
)
def load_to_redis(
    forecasts: dict[int, ProviderForecast],
    region: str,
    analysis_time: datetime,
    redis_manager: Any,  # Your SyncRedisManager
) -> int:
    """
    Load forecasts to Redis with TTL.

    Async Opportunity:
        - Could be `async def load_to_redis(...)`
        - Use redis.asyncio for concurrent writes
        - Prefect handles async orchestration

    Returns:
        Number of forecasts loaded
    """
    pipeline = redis_manager.client.pipeline()
    ttl_seconds = 14 * 3600  # 14 hours

    for spot_id, forecast in forecasts.items():
        key = f"forecast:nomads:nwps:{region}:{spot_id}"
        pipeline.setex(key, ttl_seconds, forecast.to_redis_json())

    # Store last_run metadata
    last_run_key = f"forecast:nomads:nwps:{region}:last_run"
    pipeline.set(last_run_key, analysis_time.isoformat())

    pipeline.execute()

    return len(forecasts)


@task(name="get-last-run-time")
def get_last_run_time(region: str, redis_manager: Any) -> datetime | None:
    """Fetch last successful run timestamp from Redis."""
    key = f"forecast:nomads:nwps:{region}:last_run"
    value = redis_manager.client.get(key)

    if not value:
        return None

    return datetime.fromisoformat(value)


# ============================================================================
# FLOWS (Orchestration Layer)
# ============================================================================

@flow(
    name="fetch-nwps-for-region",
    retries=1,  # Flow-level retry (retries entire DAG)
    retry_delay_seconds=3600,  # 1 hour if whole flow fails
)
def fetch_nwps_region(
    region: str,
    redis_manager: Any,
    db_manager: Any,
) -> dict[str, Any]:
    """
    Fetch NWPS forecasts for a single region.

    This is the equivalent of your current `fetch_nwps(region)` Celery task,
    but broken into granular tasks for better observability and retry control.

    Flow Features:
        - Each task is independently retryable
        - Prefect UI shows which step failed
        - Can skip already-completed tasks on retry
        - Task results are cached/persisted
    """
    # Step 1: Get last run time (idempotency check)
    last_run_time = get_last_run_time(region, redis_manager)

    # Step 2: Check availability
    result = check_availability(region, last_run_time)

    if not result:
        return {
            "status": "skipped",
            "reason": "No new run available or forecast too old",
            "region": region,
        }

    analysis_time, url = result

    # Step 3: Download GRIB2 file
    output_path = Path(f"/tmp/nomads/nwps_{region}_{analysis_time:%Y%m%d_%H}.grib2")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    file_path = download_grib_file(url, output_path)

    # Step 4: Extract forecasts (Transform)
    forecasts = extract_forecasts(file_path, Region(region), db_manager)

    # Step 5: Load to Redis
    num_loaded = load_to_redis(forecasts, region, analysis_time, redis_manager)

    # Cleanup
    file_path.unlink(missing_ok=True)

    return {
        "status": "success",
        "region": region,
        "analysis_time": analysis_time,
        "forecasts_loaded": num_loaded,
    }


@flow(
    name="fetch-all-nwps-forecasts",
    description="Fetch NWPS forecasts for all enabled regions (dispatcher)",
)
def fetch_all_nwps(
    redis_manager: Any,
    db_manager: Any,
) -> list[dict[str, Any]]:
    """
    Dispatcher flow that orchestrates regional fetches.

    Parallelization:
        - Regions are processed concurrently by default
        - Prefect auto-parallelizes independent flow calls
        - Could use DaskTaskRunner for distributed execution

    Subflow Pattern:
        - Each region runs as a subflow
        - Subflow failures don't fail parent
        - Results aggregated at end
    """
    # Get enabled regions (from your config registry)
    enabled_regions = ["maui"]  # TODO: Get from provider_config_registries

    # Fan-out: Launch subflows for each region
    # Prefect automatically parallelizes these (up to concurrency limits)
    results = [
        fetch_nwps_region(region, redis_manager, db_manager)
        for region in enabled_regions
    ]

    return results


# ============================================================================
# DEPLOYMENT CONFIGURATION (replaces Celery Beat schedule)
# ============================================================================
#
# To schedule this flow (equivalent to your Celery Beat crontab):
#
# prefect deployment build flows/nwps.py:fetch_all_nwps \
#   --name "nwps-morning" \
#   --cron "0 10 * * *" \
#   --timezone "UTC"
#
# Then create deployments for:
#   - "nwps-midday": cron "0 14 * * *"
#   - "nwps-evening": cron "0 21 * * *"
#
# Or use prefect.yaml for declarative deployments:
#
# deployments:
#   - name: nwps-morning
#     entrypoint: flows/nwps.py:fetch_all_nwps
#     schedule:
#       cron: "0 10 * * *"
#       timezone: UTC
#     parameters:
#       redis_manager: "{{ prefect.blocks.redis.forecast-redis }}"
#       db_manager: "{{ prefect.blocks.sqlalchemy.forecast-db }}"
#
# ============================================================================


# ============================================================================
# ASYNC + DASK IMPROVEMENTS (Future Enhancements)
# ============================================================================
#
# 1. ASYNC TASKS (Better I/O Concurrency)
# ────────────────────────────────────────
#
# @task
# async def download_grib_file(url: str, output_path: Path) -> Path:
#     async with httpx.AsyncClient() as client:
#         async with client.stream("GET", url) as response:
#             async with aiofiles.open(output_path, "wb") as f:
#                 async for chunk in response.aiter_bytes():
#                     await f.write(chunk)
#     return output_path
#
# @flow
# async def fetch_all_nwps(...):
#     results = await asyncio.gather(*[
#         fetch_nwps_region(region, ...)
#         for region in enabled_regions
#     ])
#     return results
#
#
# 2. DASK INTEGRATION (Parallel xarray Operations)
# ─────────────────────────────────────────────────
#
# from prefect_dask import DaskTaskRunner
# import xarray as xr
#
# @flow(task_runner=DaskTaskRunner())
# def fetch_nwps_region(...):
#     # Tasks in this flow run on Dask cluster
#     ...
#
# # In extract_forecasts:
# ds = xr.open_dataset(file_path, chunks={"time": 10})  # Lazy loading
# # Operations are parallelized across Dask workers
#
#
# 3. HYBRID APPROACH (Async + Dask)
# ──────────────────────────────────
#
# @task
# async def extract_forecasts_parallel(
#     file_path: Path,
#     spots: list[dict],
# ) -> list[ProviderForecast]:
#     # Use async for I/O, Dask for compute
#     import dask.array as da
#
#     ds = xr.open_dataset(file_path, chunks="auto")
#     # Parallel KDTree building, vectorized extraction
#     ...
#
# ============================================================================


# ============================================================================
# RESOURCE MANAGEMENT PATTERN
# ============================================================================
#
# Option A: Prefect Blocks (Production)
# ──────────────────────────────────────
#
# from prefect_redis import RedisBlock
# from prefect_sqlalchemy import DatabaseBlock
#
# @flow
# def fetch_all_nwps():
#     redis_block = RedisBlock.load("forecast-redis")
#     db_block = DatabaseBlock.load("forecast-db")
#
#     with redis_block.get_client() as redis_client:
#         with db_block.get_connection() as db_conn:
#             # Use connections
#             ...
#
#
# Option B: Dependency Injection (Simple)
# ────────────────────────────────────────
#
# from core.redis import SyncRedisManager
# from core.database import SyncDatabaseManager
#
# # In your worker entrypoint (like workers/worker_app.py):
# redis_mgr = SyncRedisManager()
# db_mgr = SyncDatabaseManager()
#
# # Pass to flow
# fetch_all_nwps.with_options(
#     parameters={"redis_manager": redis_mgr, "db_manager": db_mgr}
# ).deploy(...)
#
# ============================================================================
