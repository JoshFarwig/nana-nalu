# Celery Synchronous Architecture for Forecast Service

## Executive Summary

**Decision: Use synchronous code for Celery workers** - This is the simplest, most maintainable approach.

**Key Principle**: Keep FastAPI async, keep Celery sync. No code-sharing complications, clean separation of concerns.

**Why Sync?**
1. ✅ Celery prefork = multiprocessing (not asyncio) - true CPU parallelism
2. ✅ Tasks are CPU-bound (GRIB2 parsing, NetCDF extraction) - GIL makes async useless
3. ✅ Infrequent tasks (1-2x per day for NWPS, every 3-6 hours for APIs) - no need for high concurrency
4. ✅ Few DB queries per task (1-3 max) - NullPool is perfect
5. ✅ Simpler debugging, monitoring, and maintenance

**From async_celery.md:**
> "For CPU-intensive operations like xarray/GRIB parsing, asyncio.to_thread() provides minimal benefit due to Python's Global Interpreter Lock—multiprocessing with ProcessPoolExecutor delivers 10× better performance."

**Celery prefork pool IS multiprocessing** - you get this for free!

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ FastAPI (main process)                                      │
│ - AsyncDatabaseManager (pool_size=10)                       │
│ - AsyncSession                                              │
│ - Async Repositories                                        │
│ - Handles HTTP requests                                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Celery Master Process                                       │
│ - Manages worker processes                                  │
│ - Schedules tasks (Celery Beat)                             │
│ - Communicates with Redis broker                            │
└─────────────────────────────────────────────────────────────┘
                            │
                         fork()
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ Worker 1      │  │ Worker 2      │  │ Worker 3      │
│               │  │               │  │               │
│ Sync Engine   │  │ Sync Engine   │  │ Sync Engine   │
│ (NullPool)    │  │ (NullPool)    │  │ (NullPool)    │
│ Sync Repo     │  │ Sync Repo     │  │ Sync Repo     │
│ Redis client  │  │ Redis client  │  │ Redis client  │
│               │  │               │  │               │
│ Runs tasks    │  │ Runs tasks    │  │ Runs tasks    │
│ synchronously │  │ synchronously │  │ synchronously │
└───────────────┘  └───────────────┘  └───────────────┘
```

**Key Points:**
- Each worker process is a separate Python interpreter (separate GIL)
- Workers run tasks synchronously (no event loop)
- True parallelism across CPU cores
- Simple, predictable execution model

---

## Component Architecture

### 1. Synchronous Database Manager (Celery)

Create a separate manager for Celery workers with **NullPool** (no connection pooling).

**File**: `backend/workers/database.py`

```python
import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from core.configs import DatabaseConfig


class SyncDatabaseManager:
    """
    Synchronous Database Manager for Celery workers.
    Uses NullPool - no connection pooling (creates fresh connection per query).

    Why NullPool?
    - Each task makes 1-3 queries max
    - Tasks are infrequent (hourly/daily)
    - Avoids connection pool issues across forked processes
    - Production-proven (Apache Superset uses this pattern)
    """

    def __init__(self, settings: DatabaseConfig):
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.database_url = settings.get_sync_url()  # Note: sync URL, not async
        self._engine = None
        self._session_factory = None

    def _create_engine(self):
        """Create synchronous engine with NullPool."""
        self.logger.info("Creating sync engine with NullPool for Celery worker")

        return create_engine(
            self.database_url,
            poolclass=NullPool,  # No pooling - fresh connection per query
            pool_pre_ping=True,  # Verify connection health
            echo=False,  # Set True for SQL debugging
        )

    def _create_session_factory(self) -> sessionmaker:
        """Create synchronous session factory."""
        return sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    @property
    def engine(self):
        """Get the database engine, creating it if necessary."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> sessionmaker:
        """Get the session factory, creating it if necessary."""
        if self._session_factory is None:
            self._session_factory = self._create_session_factory()
        return self._session_factory

    @contextmanager
    def session_context(self) -> Generator[Session, None, None]:
        """
        Get a database session using context manager.

        Usage:
            with db_manager.session_context() as session:
                spots = session.query(SurfSpot).all()
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            with self.session_context() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return False

    def close(self) -> None:
        """Close the database engine."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
```

**Why NullPool?**
- From search results: "SQLAlchemy objects are often short lived in Celery workers, which means a related connection pool would be mostly useless"
- Apache Superset (production app) uses NullPool for Celery workers
- Overhead: ~1-5ms per connection (negligible for tasks running every few hours)
- Eliminates ALL multiprocessing connection sharing issues

---

### 2. Synchronous Repository (Celery)

Create sync versions of repositories needed by Celery tasks.

**File**: `backend/workers/repositories/surf_spot_repository.py`

```python
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_MakeEnvelope, ST_Within, ST_Y, ST_X

from models.surf_spot_model import SurfSpot
from utils.geo import valid_latitude_range, valid_longitude_range


class SyncSurfSpotRepository:
    """
    Synchronous repository for Celery workers.
    Only includes methods needed by forecast tasks.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, surf_spot_id: int) -> SurfSpot | None:
        """Get surf spot by ID."""
        return self.session.execute(
            select(SurfSpot).where(SurfSpot.id == surf_spot_id)
        ).scalar_one_or_none()

    def get_by_is_active(self, is_active: bool) -> Sequence[SurfSpot]:
        """Get surf spots by active status."""
        return self.session.execute(
            select(SurfSpot).where(SurfSpot.is_active == is_active)
        ).scalars().all()

    def get_all_in_grid(
        self,
        lat_min: float,
        lat_max: float,
        long_min: float,
        long_max: float,
        is_active: bool = True,
    ) -> Sequence[dict]:
        """
        Get spot IDs with coordinates from a grid.

        Returns list of dicts: [{"id": 1, "latitude": 20.9, "longitude": -156.4}, ...]
        """
        if not valid_latitude_range(lat_min, lat_max) or not valid_longitude_range(
            long_min, long_max, range_type="signed"
        ):
            raise ValueError("latitude and longitude values are invalid")

        bbox = ST_MakeEnvelope(long_min, lat_min, long_max, lat_max, 4326)

        query = select(
            SurfSpot.id,
            ST_Y(SurfSpot.location).label("latitude"),
            ST_X(SurfSpot.location).label("longitude"),
        ).where(SurfSpot.is_active == is_active, ST_Within(SurfSpot.location, bbox))

        results = self.session.execute(query)

        # Convert to list of dicts
        return [
            {
                "id": row.id,
                "latitude": row.latitude,
                "longitude": row.longitude,
            }
            for row in results
        ]

    def get_coordinates(self, surf_spot_id: int) -> dict | None:
        """Get latitude and longitude of a surf spot."""
        result = self.session.execute(
            select(
                SurfSpot.id,
                ST_Y(SurfSpot.location).label("latitude"),
                ST_X(SurfSpot.location).label("longitude"),
            ).where(SurfSpot.id == surf_spot_id)
        ).one_or_none()

        if not result:
            return None

        return {
            "id": result.id,
            "latitude": result.latitude,
            "longitude": result.longitude,
        }
```

**Key Changes from Async Version:**
- `Session` instead of `AsyncSession`
- No `async`/`await` keywords
- Direct execution (no event loop)
- Only includes methods needed by Celery tasks (YAGNI)

---

### 3. Redis Configuration (Celery)

Use standard synchronous `redis-py` with minimal connections.

**File**: `backend/workers/redis_client.py`

```python
import redis
from core.configs import RedisConfig


class SyncRedisClient:
    """
    Synchronous Redis client for Celery workers.
    Creates fresh connection per task (similar to NullPool pattern).
    """

    def __init__(self, settings: RedisConfig):
        self.settings = settings
        self._client = None

    def get_client(self) -> redis.Redis:
        """
        Get Redis client.

        For Celery tasks, you can either:
        1. Create fresh client per task (simplest)
        2. Use small connection pool per worker

        Option 1 is shown here (recommended for infrequent tasks).
        """
        return redis.from_url(
            self.settings.url.get_secret_value(),
            decode_responses=True,  # Auto-decode bytes to strings
            socket_connect_timeout=5,
            socket_timeout=5,
        )

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            client = self.get_client()
            client.ping()
            return True
        except Exception:
            return False


# Alternative: Shared connection pool per worker (if tasks are frequent)
class SyncRedisPoolClient:
    """
    Redis client with connection pooling for frequent tasks.
    Pool is shared within a single worker process.
    """

    def __init__(self, settings: RedisConfig):
        self.settings = settings
        self._pool = None

    @property
    def pool(self):
        """Lazy-create connection pool."""
        if self._pool is None:
            self._pool = redis.ConnectionPool.from_url(
                self.settings.url.get_secret_value(),
                max_connections=2,  # Small pool per worker
                decode_responses=True,
            )
        return self._pool

    def get_client(self) -> redis.Redis:
        """Get Redis client from pool."""
        return redis.Redis(connection_pool=self.pool)

    def close(self):
        """Close connection pool."""
        if self._pool:
            self._pool.disconnect()
            self._pool = None
```

**Recommendation**: Use `SyncRedisClient` (fresh connection per task) unless tasks run very frequently (every few minutes).

---

### 4. Celery Worker Configuration

**File**: `backend/workers/app.py`

```python
from celery import Celery
from celery.schedules import crontab
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
    worker_pool='prefork',  # Multiprocessing (NOT asyncio)
    worker_concurrency=4,   # Number of worker processes (match CPU cores)
    worker_prefetch_multiplier=1,  # Fetch 1 task at a time per worker
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (prevent memory leaks)

    # Result backend
    result_expires=3600,  # 1 hour

    # Task routes (organize by queue)
    task_routes={
        'workers.tasks.nwps.*': {'queue': 'nwps'},
        'workers.tasks.surfline.*': {'queue': 'surfline'},
        'workers.tasks.open_meteo.*': {'queue': 'open_meteo'},
    },
)

# Celery Beat Schedule (periodic tasks)
app.conf.beat_schedule = {
    # NWPS - Runs at 00Z and 12Z (add 30min delay for NOAA processing)
    'fetch-nwps-maui-00z': {
        'task': 'workers.tasks.nwps.fetch_nwps_forecast',
        'schedule': crontab(hour=0, minute=30),
        'kwargs': {'region': 'maui'},
    },
    'fetch-nwps-maui-12z': {
        'task': 'workers.tasks.nwps.fetch_nwps_forecast',
        'schedule': crontab(hour=12, minute=30),
        'kwargs': {'region': 'maui'},
    },

    # Surfline - Priority spots every 10min, all spots every 3 hours
    'fetch-surfline-priority': {
        'task': 'workers.tasks.surfline.fetch_surfline_forecasts',
        'schedule': crontab(minute='*/10'),
        'kwargs': {'priority': 'high'},  # Top 20 spots
    },
    'fetch-surfline-all': {
        'task': 'workers.tasks.surfline.fetch_surfline_forecasts',
        'schedule': crontab(hour='*/3', minute=0),
        'kwargs': {'priority': 'all'},  # All spots
    },

    # Open-Meteo - Every 6 hours (free, good quality)
    'fetch-open-meteo-maui': {
        'task': 'workers.tasks.open_meteo.fetch_open_meteo_forecasts',
        'schedule': crontab(hour='*/6', minute=0),
        'kwargs': {'region': 'maui'},
    },
}

# Import tasks to register them
from workers.tasks import nwps, surfline, open_meteo  # noqa
```

---

### 5. Task Structure (File-Based Providers)

**File**: `backend/workers/tasks/nwps.py`

```python
from celery import shared_task
from datetime import datetime, timezone
import logging
import json
from pathlib import Path

from workers.database import SyncDatabaseManager
from workers.repositories.surf_spot_repository import SyncSurfSpotRepository
from workers.redis_client import SyncRedisClient
from core.configs import get_settings
from services.forecast.providers.nwps.provider import NWPSProvider
from services.forecast.providers.nwps.config import get_nwps_config

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def fetch_nwps_forecast(self, region: str):
    """
    Fetch NWPS forecast for a region.

    This task:
    1. Downloads GRIB2 file (~20MB for your dataset)
    2. Extracts forecast data for all spots in region
    3. Stores raw provider data in Redis
    4. Cleans up temporary file

    Runs 2x per day (00Z, 12Z model runs).
    """
    try:
        logger.info(f"[NWPS] Starting forecast fetch for region: {region}")
        settings = get_settings()

        # Initialize database manager (NullPool - fresh connection per query)
        db_manager = SyncDatabaseManager(settings.db)

        # Initialize Redis client (fresh connection)
        redis_client = SyncRedisClient(settings.redis).get_client()

        # Get NWPS configuration for region
        nwps_config = get_nwps_config(region)

        # Get all spots in region from database
        with db_manager.session_context() as session:
            repo = SyncSurfSpotRepository(session)
            spots = repo.get_all_in_grid(
                lat_min=nwps_config.coverage["lat_min"],
                lat_max=nwps_config.coverage["lat_max"],
                long_min=nwps_config.coverage["lon_min"],
                long_max=nwps_config.coverage["lon_max"],
                is_active=True,
            )
            logger.info(f"[NWPS] Found {len(spots)} active spots in region")

        # Initialize NWPS provider (synchronous)
        provider = NWPSProvider(config=nwps_config)

        # Download GRIB2 file
        analysis_time = datetime.now(timezone.utc)
        file_path = provider.download_file(analysis_time)  # Sync download
        logger.info(f"[NWPS] Downloaded GRIB2 file: {file_path}")

        # Extract forecasts for all spots (synchronous xarray operations)
        # This is CPU-bound, benefits from prefork parallelism if multiple tasks run
        forecasts = provider.extract_forecasts(file_path, spots)
        logger.info(f"[NWPS] Extracted forecasts for {len(forecasts)} spots")

        # Store in Redis (one key per spot per timestamp)
        stored_count = 0
        for spot_id, forecast_data in forecasts.items():
            # Each forecast has multiple timestamps (144 hours)
            for timestamp, data in forecast_data.items():
                key = f"forecast:nwps:{spot_id}:{timestamp}"
                redis_client.set(
                    key,
                    json.dumps(data),
                    ex=50400  # TTL: 14 hours (expires before next model run)
                )
                stored_count += 1

        logger.info(f"[NWPS] Stored {stored_count} forecast entries in Redis")

        # Cleanup temporary file
        if file_path.exists():
            file_path.unlink()
            logger.info(f"[NWPS] Cleaned up temporary file")

        return {
            'region': region,
            'spots_processed': len(forecasts),
            'entries_stored': stored_count,
            'analysis_time': analysis_time.isoformat(),
        }

    except Exception as e:
        logger.error(f"[NWPS] Error fetching forecast: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e)
```

**Key Points:**
- Synchronous from top to bottom
- NullPool creates fresh DB connection automatically
- Fresh Redis connection per task
- xarray operations are CPU-bound - benefit from prefork parallelism
- Simple error handling and retry logic

---

### 6. Task Structure (API-Based Providers)

**File**: `backend/workers/tasks/surfline.py`

```python
from celery import shared_task
from datetime import datetime, timezone
import logging
import json
import time

from workers.database import SyncDatabaseManager
from workers.repositories.surf_spot_repository import SyncSurfSpotRepository
from workers.redis_client import SyncRedisClient
from core.configs import get_settings
from services.forecast.providers.surfline.provider import SurflineProvider

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def fetch_surfline_forecasts(self, priority: str = 'all'):
    """
    Fetch Surfline forecasts.

    Priority levels:
    - 'high': Top 20 most popular spots (runs every 10 min)
    - 'all': All spots with Surfline data (runs every 3 hours)

    Sequential requests with rate limiting (no async needed).
    """
    try:
        logger.info(f"[Surfline] Starting forecast fetch (priority: {priority})")
        settings = get_settings()

        # Initialize managers
        db_manager = SyncDatabaseManager(settings.db)
        redis_client = SyncRedisClient(settings.redis).get_client()

        # Get spots from database
        with db_manager.session_context() as session:
            repo = SyncSurfSpotRepository(session)

            if priority == 'high':
                # Get high-priority spots (would need a DB field or hardcoded list)
                # For now, just get first 20 active spots
                all_spots = repo.get_by_is_active(True)
                spots = all_spots[:20]
            else:
                # Get all active spots with Surfline data
                spots = repo.get_by_is_active(True)

            logger.info(f"[Surfline] Fetching forecasts for {len(spots)} spots")

        # Initialize Surfline provider (synchronous HTTP client)
        provider = SurflineProvider(api_key=settings.surfline.api_key)

        # Fetch forecasts (sequential with rate limiting - simple!)
        forecasts_stored = 0
        for spot in spots:
            if not spot.surfline_spot_id:
                continue

            try:
                # Sync HTTP request (uses requests library, not aiohttp)
                forecast_data = provider.fetch_forecast(spot.surfline_spot_id)

                # Store in Redis (multiple timestamps per spot)
                timestamp = datetime.now(timezone.utc)
                for hour_offset, data in enumerate(forecast_data):
                    forecast_time = timestamp + timedelta(hours=hour_offset)
                    key = f"forecast:surfline:{spot.id}:{forecast_time.isoformat()}"
                    redis_client.set(
                        key,
                        json.dumps(data),
                        ex=21600  # TTL: 6 hours
                    )
                    forecasts_stored += 1

                # Rate limiting (simple sleep - no async complexity)
                time.sleep(0.1)  # 10 requests per second max

            except Exception as e:
                logger.warning(f"[Surfline] Failed to fetch for spot {spot.id}: {e}")
                continue  # Skip failed spot, continue with others

        logger.info(f"[Surfline] Stored {forecasts_stored} forecast entries")

        return {
            'priority': priority,
            'spots_attempted': len(spots),
            'entries_stored': forecasts_stored,
        }

    except Exception as e:
        logger.error(f"[Surfline] Error: {e}", exc_info=True)
        raise self.retry(exc=e)
```

**Key Points:**
- Sequential HTTP requests with `time.sleep()` rate limiting (simple!)
- No asyncio, no event loops, no complexity
- Each worker can process different priority levels in parallel
- Rate limiting is trivial with sync code

---

### 7. Synchronous Provider Base Class

Update your provider base to support both sync and async contexts.

**File**: `backend/services/forecast/providers/base.py`

```python
from typing import Protocol, runtime_checkable
from pathlib import Path
from datetime import datetime


@runtime_checkable
class SyncFileBasedProvider(Protocol):
    """
    Protocol for file-based forecast providers (synchronous).

    Used by: NWPS, PacIOOS GridDAP
    """

    provider_name: str
    processing_mode: str  # "file_based"
    update_frequency_hours: int

    def download_file(self, analysis_time: datetime) -> Path:
        """Download regional file (GRIB2, NetCDF). Returns file path."""
        ...

    def extract_forecasts(self, file_path: Path, spots: list[dict]) -> dict:
        """
        Extract forecast data for multiple spots from file.

        Args:
            file_path: Path to downloaded file
            spots: List of dicts [{"id": 1, "latitude": 20.9, "longitude": -156.4}, ...]

        Returns:
            Dict mapping spot_id to forecast data:
            {
                "spot_id_1": {
                    "2025-01-19T12:00:00Z": {"swh": 4.5, "perpw": 12, ...},
                    "2025-01-19T13:00:00Z": {"swh": 4.3, "perpw": 11, ...},
                    ...
                },
                ...
            }
        """
        ...


@runtime_checkable
class SyncAPIBasedProvider(Protocol):
    """
    Protocol for API-based forecast providers (synchronous).

    Used by: Surfline, Open-Meteo
    """

    provider_name: str
    processing_mode: str  # "api_based"
    update_frequency_hours: int
    supports_batching: bool

    def fetch_forecast(self, spot_id: str) -> dict:
        """
        Fetch forecast for a single spot (for non-batching providers like Surfline).

        Returns raw provider data.
        """
        ...

    def fetch_forecasts_batch(self, spots: list[dict]) -> dict:
        """
        Fetch forecasts for multiple spots in one request (for batching providers like Open-Meteo).

        Args:
            spots: List of dicts [{"id": 1, "latitude": 20.9, "longitude": -156.4}, ...]

        Returns:
            Dict mapping spot_id to forecast data
        """
        ...
```

---

## Implementation Plan (Refactored for Sync)

### Phase 1: Core Infrastructure (Week 1)

**Create sync infrastructure for Celery:**

1. **`backend/workers/database.py`** - SyncDatabaseManager with NullPool ✅
2. **`backend/workers/redis_client.py`** - SyncRedisClient ✅
3. **`backend/workers/repositories/surf_spot_repository.py`** - SyncSurfSpotRepository ✅
4. **`backend/workers/app.py`** - Celery app configuration ✅

**Test sync infrastructure:**
```python
# backend/workers/test_sync_setup.py
from workers.database import SyncDatabaseManager
from workers.redis_client import SyncRedisClient
from workers.repositories.surf_spot_repository import SyncSurfSpotRepository
from core.configs import get_settings

def test_sync_setup():
    settings = get_settings()

    # Test database
    db = SyncDatabaseManager(settings.db)
    assert db.health_check()

    # Test repository
    with db.session_context() as session:
        repo = SyncSurfSpotRepository(session)
        spots = repo.get_by_is_active(True)
        print(f"Found {len(spots)} active spots")

    # Test Redis
    redis = SyncRedisClient(settings.redis)
    assert redis.health_check()

    print("✅ All sync components working!")

if __name__ == "__main__":
    test_sync_setup()
```

### Phase 2: File-Based Providers (Week 2)

**Create sync NWPS provider:**

5. **`backend/services/forecast/providers/nwps/sync_provider.py`** - Synchronous NWPS provider
   ```python
   import xarray as xr
   import requests
   from pathlib import Path
   from datetime import datetime

   class SyncNWPSProvider:
       """Synchronous NWPS provider for Celery tasks."""

       def download_file(self, analysis_time: datetime) -> Path:
           """Download GRIB2 file using requests (sync HTTP)."""
           url = self._build_url(analysis_time)
           response = requests.get(url, stream=True, timeout=300)
           response.raise_for_status()

           file_path = Path(f"/tmp/nwps_{analysis_time.isoformat()}.grib2")
           with open(file_path, 'wb') as f:
               for chunk in response.iter_content(chunk_size=8192):
                   f.write(chunk)

           return file_path

       def extract_forecasts(self, file_path: Path, spots: list[dict]) -> dict:
           """Extract forecasts using xarray (CPU-bound operation)."""
           # Open GRIB2 file
           ds = xr.open_dataset(
               file_path,
               engine='cfgrib',
               filter_by_keys={'dataType': 'fc'}
           )

           forecasts = {}
           for spot in spots:
               spot_data = ds.sel(
                   latitude=spot["latitude"],
                   longitude=spot["longitude"],
                   method='nearest'
               )

               # Extract all forecast hours
               forecasts[spot["id"]] = {}
               for time_idx, time_val in enumerate(spot_data.time.values):
                   timestamp = pd.Timestamp(time_val).isoformat()
                   forecasts[spot["id"]][timestamp] = {
                       "swh": float(spot_data["swh"].values[time_idx]),
                       "shts": float(spot_data["shts"].values[time_idx]),
                       "perpw": float(spot_data["perpw"].values[time_idx]),
                       "dirpw": float(spot_data["dirpw"].values[time_idx]),
                       # ... other GRIB variables
                   }

           ds.close()
           return forecasts
   ```

6. **`backend/workers/tasks/nwps.py`** - NWPS Celery task (see above) ✅

**Test NWPS task manually:**
```bash
# Start Celery worker
celery -A workers.app worker --loglevel=info --concurrency=2

# In another terminal, trigger task
python -c "from workers.tasks.nwps import fetch_nwps_forecast; fetch_nwps_forecast.delay('maui')"
```

### Phase 3: API-Based Providers (Week 3)

**Create sync API providers:**

7. **`backend/services/forecast/providers/surfline/sync_provider.py`** - Sync Surfline provider
   ```python
   import requests

   class SyncSurflineProvider:
       """Synchronous Surfline provider using requests library."""

       def __init__(self, api_key: str):
           self.api_key = api_key
           self.base_url = "https://services.surfline.com/kbyg/spots/forecasts"

       def fetch_forecast(self, surfline_spot_id: str) -> dict:
           """Fetch forecast for single spot (synchronous HTTP request)."""
           url = f"{self.base_url}/wave"
           params = {
               "spotId": surfline_spot_id,
               "days": 6,
               "intervalHours": 1,
           }
           headers = {"Authorization": self.api_key} if self.api_key else {}

           response = requests.get(url, params=params, headers=headers, timeout=10)
           response.raise_for_status()

           return response.json()
   ```

8. **`backend/services/forecast/providers/open_meteo/sync_provider.py`** - Sync Open-Meteo provider (batching)
9. **`backend/workers/tasks/surfline.py`** - Surfline task ✅
10. **`backend/workers/tasks/open_meteo.py`** - Open-Meteo task

### Phase 4: Integration & Testing (Week 4)

11. **Update Celery Beat schedule** in `workers/app.py` ✅
12. **Add monitoring/logging** - Flower dashboard
13. **Integration testing** - Run all tasks, verify Redis data
14. **Load testing** - Multiple tasks in parallel (verify prefork parallelism)

---

## Running Celery

### Development

```bash
# Terminal 1: Start worker
celery -A workers.app worker --loglevel=info --concurrency=2

# Terminal 2: Start beat (scheduler)
celery -A workers.app beat --loglevel=info

# Terminal 3: Monitor with Flower
celery -A workers.app flower --port=5555
# Visit http://localhost:5555
```

### Production

```bash
# Worker (background daemon)
celery -A workers.app worker \
  --loglevel=info \
  --concurrency=4 \
  --max-tasks-per-child=100 \
  --time-limit=300 \
  --soft-time-limit=240

# Beat (background daemon)
celery -A workers.app beat --loglevel=info

# Flower (monitoring)
celery -A workers.app flower --port=5555 --broker_api=redis://localhost:6379/0
```

---

## Benefits of Synchronous Approach

### ✅ Simplicity
- No event loop management
- No async/await complexity
- Straightforward debugging
- Standard Python idioms

### ✅ Performance
- Prefork pool = true CPU parallelism (separate GIL per process)
- No GIL bottleneck for GRIB parsing (each worker has own interpreter)
- NullPool overhead negligible (1-5ms per connection, tasks run hourly/daily)

### ✅ Reliability
- No connection pool corruption across processes (NullPool prevents this)
- No event loop lifecycle issues
- Proven production pattern (Apache Superset, many others)

### ✅ Maintainability
- Clear separation: FastAPI = async, Celery = sync
- No shared code complications
- Easy to onboard new developers
- Predictable behavior

### ✅ Resource Efficiency
- NullPool: No wasted connections sitting idle
- Fresh Redis connections: No pool exhaustion
- Worker recycling (max_tasks_per_child): Prevents memory leaks

---

## Performance Expectations

### NWPS (File-Based, 2x/day)
- **Download**: 20MB GRIB2 in 3-10 seconds (sync HTTP)
- **Extraction**: 20 spots × 144 hours in 30-60 seconds (xarray CPU-bound)
- **Redis storage**: 20 spots × 144 entries in 2-5 seconds
- **Total**: ~1-2 minutes per run
- **Network**: 40MB/day (2 runs × 20MB)

### Surfline (API-Based, Priority: 10min, All: 3hr)
- **Per-spot request**: 100-200ms (sync HTTP + rate limit)
- **Priority (20 spots)**: 20 × 0.2s = 4 seconds per run
- **All spots (150)**: 150 × 0.2s = 30 seconds per run
- **Network**: ~70MB/day (similar to your estimate)

### Open-Meteo (API-Based, Batched, Every 6hr)
- **Batch request (150 spots)**: 1-2 seconds (single HTTP request)
- **Network**: ~5MB/day (4 runs × ~1.2MB)

### Parallelism with Prefork (4 workers)
If multiple tasks are scheduled at the same time:
- Worker 1: NWPS task (60 sec)
- Worker 2: Surfline high priority (4 sec)
- Worker 3: Open-Meteo (2 sec)
- Worker 4: Idle

**Total wall-clock time**: 60 seconds (vs 66 seconds sequential)

---

## Migration from Existing Async Code

### What to Keep (FastAPI)
- ✅ `backend/core/database.py` - AsyncDatabaseManager
- ✅ `backend/repositories/*_repository.py` - Async repositories
- ✅ All FastAPI routes and dependencies
- ✅ Async HTTP managers

### What to Create (Celery)
- ✅ `backend/workers/database.py` - SyncDatabaseManager (new)
- ✅ `backend/workers/repositories/` - Sync repositories (new, minimal)
- ✅ `backend/workers/tasks/` - Celery tasks (new)
- ✅ `backend/services/forecast/providers/*/sync_provider.py` - Sync providers (new)

### Code Duplication?
**Minimal and justified:**
- Database manager: ~100 lines (NullPool vs AsyncEngine - fundamentally different)
- Repository: ~50 lines per repo (only methods used by tasks)
- Providers: Can share business logic, just different HTTP clients (requests vs aiohttp)

**Total duplication**: <500 lines for complete sync infrastructure

**Trade-off**: 500 lines of simple sync code vs complex async wrappers, event loop management, and multiprocessing issues.

---

## Conclusion

**The synchronous approach is the right choice for your forecast service:**

1. ✅ **Celery prefork = multiprocessing** (not asyncio) - sync is natural fit
2. ✅ **CPU-bound tasks** (GRIB parsing) benefit from true parallelism, not async
3. ✅ **Infrequent tasks** don't need high concurrency
4. ✅ **Simple, maintainable code** - no event loop complexity
5. ✅ **Production-proven pattern** - Apache Superset and many others use this
6. ✅ **NullPool perfect for your use case** - 1-3 queries per task, tasks run hourly/daily
7. ✅ **Clean separation** - FastAPI async, Celery sync - each tool used as intended

**Async would only add complexity with no benefits** for this specific use case.
