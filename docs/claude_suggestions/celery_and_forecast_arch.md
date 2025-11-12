## Architecture Recommendations

### 1. **Forecasting Service Architecture - Adapter Pattern**

The adapter pattern is excellent for your multi-source forecasting needs. Here's a flexible architecture:

```python
# backend/services/forecast/base.py
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable
from datetime import datetime
from pydantic import BaseModel

class ForecastData(BaseModel):
    """Unified forecast data model"""
    timestamp: datetime
    wave_height: float | None = None
    wave_period: float | None = None
    wave_direction: float | None = None
    swell_height: float | None = None
    swell_period: float | None = None
    swell_direction: float | None = None
    wind_speed: float | None = None
    wind_direction: float | None = None
    tide_height: float | None = None
    
@runtime_checkable
class ForecastProvider(Protocol):
    """Protocol for forecast providers"""
    async def fetch_forecast(
        self, 
        lat: float, 
        lon: float,
        start: datetime,
        end: datetime
    ) -> list[ForecastData]:
        ...
    
    @property
    def provider_name(self) -> str:
        ...
    
    def is_available_for_spot(self, spot_id: str) -> bool:
        ...
```

### 2. **Provider Registry Pattern**

```python
# backend/services/forecast/registry.py
from typing import Dict, List
import logging

class ForecastRegistry:
    """Registry for managing forecast providers"""
    
    def __init__(self):
        self._providers: Dict[str, ForecastProvider] = {}
        self._spot_providers: Dict[str, List[str]] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_provider(
        self, 
        name: str, 
        provider: ForecastProvider
    ) -> None:
        self._providers[name] = provider
        
    def register_spot_provider(
        self, 
        spot_id: str, 
        provider_names: List[str]
    ) -> None:
        self._spot_providers[spot_id] = provider_names
        
    def get_providers_for_spot(
        self, 
        spot_id: str
    ) -> List[ForecastProvider]:
        provider_names = self._spot_providers.get(spot_id, [])
        return [
            self._providers[name] 
            for name in provider_names 
            if name in self._providers
        ]
```

### 3. **HTTP Manager for External APIs**

```python
# backend/services/forecast/http_manager.py
import httpx
from typing import Optional
import logging

class ForecastHTTPManager:
    """Manages HTTP connections for forecast providers"""
    
    def __init__(
        self,
        timeout: int = 30,
        max_connections: int = 10,
        max_keepalive_connections: int = 5
    ):
        self.logger = logging.getLogger(__name__)
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout
        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections
        )
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=self._limits,
                headers={"User-Agent": "NanaNalu-Forecast/1.0"}
            )
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
```

## Celery Production Setup

### 1. **Celery App Configuration**

```python
# backend/celery_app/app.py
from celery import Celery
from kombu import Queue
from core import get_settings
import logging

logger = logging.getLogger(__name__)

def create_celery_app(config_name: str = None) -> Celery:
    """Create and configure Celery app"""
    settings = get_settings(config_name)
    
    app = Celery(
        'nana_nalu',
        broker=settings.redis.broker_url.get_secret_value(),
        backend=settings.redis.broker_url.get_secret_value(),
    )
    
    # Configuration
    app.conf.update(
        # Task execution
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        
        # Worker configuration
        worker_prefetch_multiplier=4,
        worker_max_tasks_per_child=1000,
        worker_disable_rate_limits=False,
        
        # Result backend
        result_expires=3600,  # 1 hour
        result_backend_transport_options={
            'master_name': 'mymaster',
            'visibility_timeout': 3600,
        },
        
        # Queue configuration
        task_routes={
            'celery_app.tasks.forecast.*': {'queue': 'forecast'},
            'celery_app.tasks.maintenance.*': {'queue': 'maintenance'},
        },
        
        task_queues=(
            Queue('celery', routing_key='celery'),
            Queue('forecast', routing_key='forecast'),
            Queue('maintenance', routing_key='maintenance'),
        ),
        
        # Beat schedule (if using)
        beat_schedule={
            'fetch-forecasts': {
                'task': 'celery_app.tasks.forecast.fetch_all_forecasts',
                'schedule': 3600.0,  # Every hour
            },
        },
    )
    
    return app

# Create the app instance
celery_app = create_celery_app()
```

### 2. **Worker Lifecycle Management**

```python
# backend/celery_app/worker.py
from celery import signals
from celery.utils.log import get_task_logger
from core import AsyncDatabaseManager, AsyncRedisManager, get_settings
from services.forecast.http_manager import ForecastHTTPManager
import asyncio

logger = get_task_logger(__name__)

class WorkerState:
    """Singleton state for worker resources"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def initialize(self, settings):
        if not self.initialized:
            self.settings = settings
            self.db_manager = AsyncDatabaseManager(settings.db)
            self.redis_manager = AsyncRedisManager(
                settings.redis, 
                settings.redis.cache_url
            )
            self.http_manager = ForecastHTTPManager()
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
@signals.worker_init.connect
def init_worker(**kwargs):
    """Initialize worker resources"""
    settings = get_settings()
    WorkerState().initialize(settings)

@signals.worker_shutdown.connect
def shutdown_worker(**kwargs):
    """Cleanup worker resources"""
    state = WorkerState()
    if state.initialized:
        state.loop.run_until_complete(state.cleanup())
```

### 3. **Task Base Class**

```python
# backend/celery_app/tasks/base.py
from celery import Task
from celery_app.worker import WorkerState
import asyncio

class AsyncTask(Task):
    """Base task with async support and resource access"""
    
    def __call__(self, *args, **kwargs):
        """Run task in async context"""
        state = WorkerState()
        return state.loop.run_until_complete(
            self.run_async(*args, **kwargs)
        )
    
    async def run_async(self, *args, **kwargs):
        """Override this in subclasses"""
        raise NotImplementedError
    
    @property
    def db_manager(self):
        return WorkerState().db_manager
    
    @property
    def redis_manager(self):
        return WorkerState().redis_manager
    
    @property
    def http_manager(self):
        return WorkerState().http_manager
```

### 4. **Docker Compose Setup**

```yaml
# docker-compose.yml
services:
  celery-worker:
    build:
      context: ./backend
      target: worker
    environment:
      - ENV=${ENV:-production}
      - C_FORCE_ROOT=true
    command: celery -A celery_app.app worker -l info -Q celery,forecast -n worker@%h
    depends_on:
      - redis
      - postgres
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 512M
          
  celery-beat:
    build:
      context: ./backend
      target: beat
    environment:
      - ENV=${ENV:-production}
    command: celery -A celery_app.app beat -l info
    depends_on:
      - redis
      - postgres
```

### 5. **Production Considerations**

**Connection Pooling Strategy:**

- Database: Use smaller pool for Celery (2-3 connections) vs FastAPI (5-10)
- Redis: Separate connection pools for broker vs cache
- HTTP: Persistent connections with reasonable keepalive

**Monitoring Setup:**

```python
# backend/celery_app/monitoring.py
from celery import signals
import logging

@signals.task_failure.connect
def log_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    logger.error(f"Task {sender.name}[{task_id}] failed: {exception}")

@signals.task_retry.connect  
def log_task_retry(sender=None, reason=None, **kwargs):
    logger.warning(f"Task {sender.name} retrying: {reason}")
```

**Error Handling:**

```python
# backend/celery_app/tasks/forecast.py
from celery import shared_task
from celery_app.tasks.base import AsyncTask

@shared_task(
    bind=True,
    base=AsyncTask,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True
)
class FetchForecastTask(AsyncTask):
    async def run_async(self, spot_id: str):
        # Your async forecast fetching logic
        pass
```

### Key Recommendations

1. **Separate connection pools** - Celery workers should have stricter, smaller pools than your API
2. **Use worker state singleton** - Avoid recreating managers per task
3. **Implement circuit breakers** for external API calls
4. **Add task result caching** in Redis with appropriate TTLs
5. **Monitor task queue depth** and worker utilization
6. **Use task routing** to separate forecast tasks from maintenance tasks
7. **Implement graceful shutdown** handlers for cleanup

This architecture provides:

- Clean separation of concerns
- Easy addition of new forecast providers
- Efficient resource management
- Production-ready error handling
- Scalable task processing

For multi-provider forecast data, I'd recommend a **hybrid approach**:

## Data Organization Strategy

### 1. **Group by Data Type, Show Provider Source**

```python
# Structure your API response like this:
{
    "spot_id": "dumps",
    "forecasts": {
        "waves": {
            "primary": {  # User's preferred or best available
                "provider": "surfline",
                "height": 4.5,
                "period": 12,
                "direction": 270
            },
            "alternatives": [
                {"provider": "wavewatch", "height": 4.2, ...},
                {"provider": "pacioos", "height": 4.8, ...}
            ]
        },
        "wind": {
            "primary": {
                "provider": "open_meteo",  # Maybe only source
                "speed": 15,
                "direction": 90
            },
            "alternatives": []
        },
        "tide": {
            "primary": {
                "provider": "noaa",
                "height": 1.2,
                "type": "rising"
            }
        }
    }
}
```

### 2. **User Preferences Table**

```python
# Store user preferences
class UserForecastPreferences:
    user_id: str
    spot_id: str  # Can be null for global preference
    wave_provider_priority: list = ["surfline", "pacioos", "wavewatch"]
    wind_provider_priority: list = ["surfline", "open_meteo"]
    show_alternatives: bool = True
    comparison_view: bool = False  # Toggle between unified/comparison
```

### 3. **Frontend Display Options**

**Default View:** Unified display with primary provider data, small indicator showing source

```
Wave: 4-6ft @ 12s WSW (Surfline ▼)
Wind: 15kts E (Open-Meteo)
```

**Expanded/Comparison View:** User clicks dropdown to see all providers

```
Wave Heights:
├─ Surfline: 4-6ft
├─ PacIOOS: 4.8ft  
└─ WaveWatch: 4.2ft
```

### Key Benefits

- **Clean default UX** - Users see one clear forecast
- **Transparency** - Always show data source
- **Power user features** - Allow comparison when needed
- **Smart fallbacks** - If preferred provider fails, use next available
- **Spot-specific optimization** - Some spots might have better accuracy from specific providers

This way users get simplicity by default but can drill down for confidence/comparison when they want it.

---

## Redis Hash Architecture for Multi-Provider Forecast Storage

### Recommended Structure: Redis Hash with Provider Namespacing

**Key Pattern:**
```
forecast:{spot_id}:{hour_timestamp}
```

**Storage Method:** Redis Hash (HSET/HGET/HGETALL)

### Hash Structure

```
forecast:dumps:2025-11-10T12 (Redis Hash)
├─ surfline:wave → '{"height": 4.5, "period": 12, "direction": 270}'
├─ surfline:wind → '{"speed": 15, "direction": 90}'
├─ noaa:tide → '{"height": 1.2, "trend": "rising"}'
├─ pacioos:wave → '{"height": 4.8, "period": 13, "direction": 265}'
├─ _primary:wave → "surfline"
├─ _primary:wind → "surfline"
├─ _primary:tide → "noaa"
├─ _meta:updated_at → "2025-11-10T12:05:32Z"
└─ _meta:expires_at → "2025-11-10T14:00:00Z"
```

### Benefits

1. **Atomic Updates**: Each provider can update independently without race conditions
   ```python
   await redis.hset("forecast:dumps:2025-11-10T12", "surfline:wave", json.dumps(data))
   ```

2. **Flexible Retrieval**:
   - Get all providers: `HGETALL forecast:dumps:2025-11-10T12`
   - Get specific provider: `HGET forecast:dumps:2025-11-10T12 surfline:wave`
   - Get all from one provider: `HGETALL` + filter by prefix

3. **Single TTL Management**: Set expiration on entire hash
   ```python
   await redis.expire("forecast:dumps:2025-11-10T12", 7200)  # 2 hours
   ```

4. **Efficient Storage**: One key per spot/hour vs multiple keys per provider

5. **Easy Provider Management**: Add/remove providers without restructuring

### Implementation Example

**Celery Task - Fetch & Store:**
```python
@shared_task(base=AsyncTask)
class FetchSurflineForecastTask(AsyncTask):
    async def run_async(self, spot_id: str):
        # Fetch from Surfline API
        data = await self.http_manager.client.get(f"https://api.surfline.com/...")

        # Current hour timestamp
        hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        key = f"forecast:{spot_id}:{hour.isoformat()}"

        # Store wave data
        await self.redis_manager.hset(
            key,
            "surfline:wave",
            json.dumps({
                "height": data["wave"]["height"],
                "period": data["wave"]["period"],
                "direction": data["wave"]["direction"]
            })
        )

        # Store wind data
        await self.redis_manager.hset(
            key,
            "surfline:wind",
            json.dumps({
                "speed": data["wind"]["speed"],
                "direction": data["wind"]["direction"]
            })
        )

        # Update metadata
        await self.redis_manager.hset(
            key,
            "_meta:updated_at",
            datetime.utcnow().isoformat()
        )

        # Set TTL (2 hours)
        await self.redis_manager.expire(key, 7200)

        return {"spot_id": spot_id, "provider": "surfline", "status": "cached"}
```

**API Endpoint - Retrieve:**
```python
@router.get("/forecast/{spot_id}")
async def get_forecast(spot_id: str, redis: Redis = Depends(get_redis)):
    hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    key = f"forecast:{spot_id}:{hour.isoformat()}"

    # Get all forecast data
    raw_data = await redis.hgetall(key)

    if not raw_data:
        return {"status": "no_data", "message": "Forecast data not available"}

    # Parse into structured response
    forecast = {
        "spot_id": spot_id,
        "timestamp": hour.isoformat(),
        "providers": {},
        "primary": {},
        "metadata": {}
    }

    for field, value in raw_data.items():
        if field.startswith("_primary:"):
            data_type = field.split(":")[1]
            forecast["primary"][data_type] = value
        elif field.startswith("_meta:"):
            meta_key = field.split(":")[1]
            forecast["metadata"][meta_key] = value
        else:
            provider, data_type = field.split(":", 1)
            if provider not in forecast["providers"]:
                forecast["providers"][provider] = {}
            forecast["providers"][provider][data_type] = json.loads(value)

    return forecast
```

### Handling Different Provider Update Intervals

**Challenge:** Providers update at different frequencies:
- PacIOOS: Daily at 3am
- Surfline: Hourly
- Open-Meteo: Every 15 minutes

**Solution: Per-Provider TTL Tracking + Smart Refresh**

#### Option 1: Field-Level Metadata (Recommended)

Store last update timestamp per provider field:

```
forecast:dumps:2025-11-10T12
├─ surfline:wave → '{"height": 4.5, ...}'
├─ surfline:wave:updated_at → "2025-11-10T12:05:00Z"
├─ pacioos:wave → '{"height": 4.8, ...}'
├─ pacioos:wave:updated_at → "2025-11-10T03:00:00Z"  # Last updated at 3am
```

**Celery Beat Schedule with Provider-Specific Intervals:**

```python
# backend/celery/app.py
app.conf.beat_schedule = {
    # Surfline - every hour
    'fetch-surfline-forecasts': {
        'task': 'celery_app.tasks.forecast.fetch_surfline_all_spots',
        'schedule': crontab(minute=0),  # Every hour at :00
    },

    # PacIOOS - daily at 3am
    'fetch-pacioos-forecasts': {
        'task': 'celery_app.tasks.forecast.fetch_pacioos_all_spots',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3:00 AM
    },

    # Open-Meteo - every 15 minutes
    'fetch-openmeteo-forecasts': {
        'task': 'celery_app.tasks.forecast.fetch_openmeteo_all_spots',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
}
```

**Smart Refresh Logic in Tasks:**

```python
@shared_task(base=AsyncTask)
class FetchProviderForecastTask(AsyncTask):
    provider_name: str = None
    update_interval: int = 3600  # seconds

    async def run_async(self, spot_id: str):
        hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        key = f"forecast:{spot_id}:{hour.isoformat()}"

        # Check if data is still fresh
        updated_at_key = f"{self.provider_name}:wave:updated_at"
        last_update = await self.redis_manager.hget(key, updated_at_key)

        if last_update:
            last_update_dt = datetime.fromisoformat(last_update)
            age = (datetime.utcnow() - last_update_dt).total_seconds()

            if age < self.update_interval:
                return {"status": "skipped", "reason": "data_still_fresh"}

        # Fetch new data
        data = await self.fetch_from_provider(spot_id)

        # Store with timestamp
        await self.redis_manager.hset(key, f"{self.provider_name}:wave", json.dumps(data))
        await self.redis_manager.hset(
            key,
            updated_at_key,
            datetime.utcnow().isoformat()
        )

        # Set TTL to longest provider interval (24h for PacIOOS)
        await self.redis_manager.expire(key, 86400)  # 24 hours

        return {"status": "updated"}


class FetchSurflineForecastTask(FetchProviderForecastTask):
    provider_name = "surfline"
    update_interval = 3600  # 1 hour

class FetchPacIOOSForecastTask(FetchProviderForecastTask):
    provider_name = "pacioos"
    update_interval = 86400  # 24 hours

class FetchOpenMeteoForecastTask(FetchProviderForecastTask):
    provider_name = "openmeteo"
    update_interval = 900  # 15 minutes
```

#### Option 2: Separate Keys with Individual TTLs

Store each provider in separate keys with their own TTLs:

```
forecast:dumps:2025-11-10T12:surfline (TTL: 2h)
forecast:dumps:2025-11-10T12:pacioos (TTL: 24h)
forecast:dumps:2025-11-10T12:openmeteo (TTL: 30min)
```

**Pros:**
- Each provider expires independently
- No stale data served

**Cons:**
- Multiple Redis calls to assemble full forecast
- More complex API logic

#### Recommended Approach: Hybrid

Use **single hash with field metadata** + **longest TTL**:

1. Set hash TTL to longest provider interval (24h for PacIOOS)
2. Track per-field update timestamps
3. API checks freshness and shows age to users
4. Celery Beat schedules each provider at its optimal interval

**API Response with Staleness Info:**

```json
{
  "spot_id": "dumps",
  "providers": {
    "surfline": {
      "wave": {"height": 4.5, ...},
      "updated_at": "2025-11-10T12:00:00Z",
      "age_minutes": 5,
      "is_fresh": true
    },
    "pacioos": {
      "wave": {"height": 4.8, ...},
      "updated_at": "2025-11-10T03:00:00Z",
      "age_minutes": 540,
      "is_fresh": true  // Still fresh if < 24h
    }
  }
}
```

### Key Takeaways

1. **Use Redis Hash** for atomic, efficient multi-provider storage
2. **Single hash per spot/hour** with provider-namespaced fields
3. **Store field-level metadata** for update timestamps
4. **Set hash TTL to longest provider interval** (24h)
5. **Celery Beat schedules per-provider** at their optimal intervals
6. **API shows data age** so users know freshness
7. **Tasks check staleness** before fetching to avoid unnecessary API calls

---

## NWPS GRIB2 Provider Architecture

### Overview: File-Based vs HTTP-Based Providers

NWPS requires a **different processing model** than traditional API providers. Instead of per-spot HTTP requests, you:
1. Download a single 62MB GRIB2 file (covers entire region)
2. Extract data for all spots from this one file
3. Store results in Redis
4. Delete the file

This requires adapting your provider pattern to support **both processing models**.

### Unified Provider Protocol with Processing Modes

**Enhanced base protocol supporting multiple processing strategies:**

```python
# backend/services/forecast/base.py
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable, Literal
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel

class ForecastData(BaseModel):
    """Unified forecast data model"""
    timestamp: datetime
    wave_height: float | None = None
    wave_period: float | None = None
    wave_direction: float | None = None
    wind_speed: float | None = None
    wind_direction: float | None = None
    water_level: float | None = None  # For NWPS tide+surge+setup


@runtime_checkable
class ForecastProvider(Protocol):
    """
    Base protocol for all forecast providers.
    Supports both per-spot (HTTP) and regional (file-based) processing.
    """

    @property
    def provider_name(self) -> str:
        """Unique identifier for this provider"""
        ...

    @property
    def processing_mode(self) -> Literal["per_spot", "regional"]:
        """
        Processing strategy:
        - "per_spot": Fetch data individually per spot (HTTP APIs)
        - "regional": Fetch once for entire region (GRIB2 files)
        """
        ...

    @property
    def update_frequency_seconds(self) -> int:
        """How often this provider updates data"""
        ...

    def is_available_for_spot(self, spot: "Spot") -> bool:
        """Check if provider covers this spot's location"""
        ...


@runtime_checkable
class PerSpotProvider(ForecastProvider, Protocol):
    """
    Provider that fetches data per-spot via HTTP.
    Examples: Surfline, Open-Meteo, NOAA APIs
    """

    async def fetch_forecast(
        self,
        spot: "Spot",
        start: datetime,
        end: datetime
    ) -> list[ForecastData]:
        """Fetch forecast for a single spot"""
        ...


@runtime_checkable
class RegionalProvider(ForecastProvider, Protocol):
    """
    Provider that processes regional data files.
    Examples: NWPS GRIB2, PacIOOS NetCDF

    Processing flow:
    1. Download/fetch regional file
    2. Extract data for all spots in region
    3. Return dict mapping spot_id → forecast data
    4. Cleanup file
    """

    @property
    def region(self) -> str:
        """Geographic region this provider covers (e.g., "hawaii")"""
        ...

    async def fetch_regional_data(
        self,
        model_run: datetime
    ) -> Path:
        """
        Download regional data file.
        Returns path to downloaded file (caller responsible for cleanup).
        """
        ...

    async def extract_spot_forecasts(
        self,
        data_file: Path,
        spots: list["Spot"],
        start: datetime,
        end: datetime
    ) -> dict[str, list[ForecastData]]:
        """
        Extract forecasts for multiple spots from data file.

        Returns:
            {spot_id: [ForecastData, ...]}
        """
        ...
```

### NWPS Provider Implementation

**Provider that implements RegionalProvider protocol:**

```python
# backend/services/forecast/providers/nwps_provider.py
from services.forecast.base import RegionalProvider, ForecastData
from pathlib import Path
from datetime import datetime, timezone
import pygrib
import httpx
from typing import Literal

class NWPSProvider:
    """
    NOAA Nearshore Wave Prediction System (NWPS) provider.

    Data source: GRIB2 files containing wave, wind, and water level forecasts.
    Update frequency: Twice daily at 00Z and 12Z.
    Coverage: Regional grids (Hawaii = CG4).
    """

    def __init__(self, region_config: dict, http_client: httpx.AsyncClient):
        """
        Args:
            region_config: {
                "code": "CG4",
                "name": "Hawaii",
                "base_url": "https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod",
                "coverage": {"lat_min": 18.5, "lat_max": 22.5, ...}
            }
            http_client: Shared HTTP client for downloads
        """
        self.region_config = region_config
        self.http_client = http_client

    # Protocol properties
    provider_name = "nwps"
    processing_mode: Literal["regional"] = "regional"
    update_frequency_seconds = 43200  # 12 hours

    @property
    def region(self) -> str:
        return self.region_config["name"].lower()

    def is_available_for_spot(self, spot) -> bool:
        """Check if spot is within NWPS grid coverage"""
        coverage = self.region_config["coverage"]
        return (
            coverage["lat_min"] <= spot.latitude <= coverage["lat_max"]
            and coverage["lon_min"] <= spot.longitude <= coverage["lon_max"]
        )

    async def fetch_regional_data(self, model_run: datetime) -> Path:
        """
        Download NWPS GRIB2 file for a model run.

        Args:
            model_run: Model initialization time (must be 00Z or 12Z)

        Returns:
            Path to downloaded GRIB2 file
        """
        # Determine model hour (00 or 12)
        model_hour = 0 if model_run.hour < 12 else 12
        run_date = model_run.strftime("%Y%m%d")

        # Build URL
        # Example: .../nwps.20251112/CG4/nwps.t00z.cg4.grib2
        code = self.region_config["code"]
        url = (
            f"{self.region_config['base_url']}/nwps.{run_date}/"
            f"{code}/nwps.t{model_hour:02d}z.{code.lower()}.grib2"
        )

        # Download to temp location
        output_file = Path(f"/tmp/nwps_{run_date}_{model_hour:02d}z_{code.lower()}.grib2")

        # Streaming download (efficient for 62MB file)
        async with self.http_client.stream("GET", url) as response:
            response.raise_for_status()

            with open(output_file, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

        return output_file

    async def extract_spot_forecasts(
        self,
        data_file: Path,
        spots: list,
        start: datetime,
        end: datetime
    ) -> dict[str, list[ForecastData]]:
        """
        Extract forecast data for all spots from GRIB2 file.

        This is the core extraction logic - reads file once,
        extracts data for all spots.
        """
        # Open GRIB2 file
        grbs = pygrib.open(str(data_file))

        # Build index of all messages by parameter and forecast hour
        # Structure: {param_name: {forecast_datetime: grib_message}}
        index = self._build_grib_index(grbs)

        grbs.close()

        # Extract data for each spot
        results = {}

        for spot in spots:
            # Extract timeseries for this spot
            timeseries = []

            # Get all unique forecast hours
            forecast_hours = self._get_forecast_hours(index)

            for forecast_hour in forecast_hours:
                if not (start <= forecast_hour <= end):
                    continue

                # Extract point data at spot's lat/lon
                forecast_data = ForecastData(
                    timestamp=forecast_hour,
                    wave_height=self._extract_value(
                        index.get("wave_height", {}).get(forecast_hour),
                        spot.latitude,
                        spot.longitude
                    ),
                    wave_period=self._extract_value(
                        index.get("wave_period", {}).get(forecast_hour),
                        spot.latitude,
                        spot.longitude
                    ),
                    wave_direction=self._extract_value(
                        index.get("wave_direction", {}).get(forecast_hour),
                        spot.latitude,
                        spot.longitude
                    ),
                    wind_speed=self._extract_value(
                        index.get("wind_speed", {}).get(forecast_hour),
                        spot.latitude,
                        spot.longitude
                    ),
                    wind_direction=self._extract_value(
                        index.get("wind_direction", {}).get(forecast_hour),
                        spot.latitude,
                        spot.longitude
                    ),
                    water_level=self._extract_value(
                        index.get("water_level", {}).get(forecast_hour),
                        spot.latitude,
                        spot.longitude
                    ),
                )

                timeseries.append(forecast_data)

            results[spot.id] = timeseries

        return results

    def _build_grib_index(self, grbs) -> dict:
        """
        Build index of GRIB messages by parameter and time.

        Returns:
            {
                "wave_height": {datetime(...): grib_message, ...},
                "wave_period": {...},
                ...
            }
        """
        index = {}

        # Map GRIB parameter names to our standardized names
        param_mapping = {
            "Significant height of combined wind waves and swell": "wave_height",
            "Primary wave mean period": "wave_period",
            "Primary wave direction": "wave_direction",
            "Wind speed": "wind_speed",
            "Wind direction": "wind_direction",
            "Water Surface Elevation": "water_level",  # tide+surge+setup
        }

        for grb in grbs:
            param_name = grb.name

            if param_name in param_mapping:
                standardized_name = param_mapping[param_name]
                forecast_time = grb.validDate  # Forecast valid time

                if standardized_name not in index:
                    index[standardized_name] = {}

                index[standardized_name][forecast_time] = grb

        return index

    def _get_forecast_hours(self, index: dict) -> list[datetime]:
        """Extract all unique forecast hours from index"""
        hours = set()
        for param_data in index.values():
            hours.update(param_data.keys())
        return sorted(hours)

    def _extract_value(
        self,
        grb_message,
        lat: float,
        lon: float
    ) -> float | None:
        """
        Extract value from GRIB message at specific lat/lon.
        Uses nearest neighbor (can be enhanced with bilinear interpolation).
        """
        if grb_message is None:
            return None

        try:
            # Get grid data and coordinates
            data, lats, lons = grb_message.data()

            # Find nearest grid point
            dist_sq = (lats - lat)**2 + (lons - lon)**2
            idx = dist_sq.argmin()
            value = data.flat[idx]

            # Check for missing values (GRIB2 uses large numbers)
            if value > 1e10 or value < -1e10:
                return None

            return float(value)

        except Exception as e:
            # Log error but don't fail entire extraction
            return None
```

### Task Orchestration for Regional Providers

**Two-task pattern: Download + Fan-out extraction**

```python
# backend/celery/tasks/nwps.py
from celery import shared_task, group
from celery_app.tasks.base import AsyncTask
from services.forecast.providers.nwps_provider import NWPSProvider
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

@shared_task(
    bind=True,
    base=AsyncTask,
    max_retries=3,
    default_retry_delay=300,  # 5 min
)
class FetchNWPSRegionalTask(AsyncTask):
    """
    Orchestrator task for NWPS data.

    Responsibilities:
    1. Download GRIB2 file
    2. Get all spots in region
    3. Fan out extraction tasks
    4. Coordinate cleanup
    """

    async def run_async(self, region: str = "hawaii"):
        self.logger.info(f"Starting NWPS fetch for region: {region}")

        # Determine current model run
        now = datetime.now(timezone.utc)
        model_hour = 0 if now.hour < 12 else 12
        model_run = now.replace(hour=model_hour, minute=0, second=0, microsecond=0)

        # Initialize provider
        provider = self._get_provider(region)

        # Download GRIB2 file
        try:
            grib_file = await provider.fetch_regional_data(model_run)
            file_size_mb = grib_file.stat().st_size / (1024 * 1024)
            self.logger.info(f"Downloaded GRIB2 file: {file_size_mb:.2f} MB")
        except Exception as e:
            self.logger.error(f"Failed to download GRIB2: {e}")
            raise

        # Store file metadata in Redis (for coordination)
        file_key = f"nwps:grib_file:{region}:{model_run.isoformat()}"
        await self.redis_manager.hset(
            file_key,
            mapping={
                "file_path": str(grib_file),
                "model_run": model_run.isoformat(),
                "region": region,
                "downloaded_at": datetime.utcnow().isoformat(),
                "file_size_mb": file_size_mb,
            }
        )
        await self.redis_manager.expire(file_key, 3600)  # 1 hour

        # Get all spots in region
        spots = await self._get_spots_in_region(region)
        self.logger.info(f"Found {len(spots)} spots in {region}")

        # Create extraction tasks for all spots
        # Each task will read the same file
        extraction_tasks = [
            extract_nwps_spot_data.s(
                spot_id=spot.id,
                file_key=file_key,
                region=region
            )
            for spot in spots
        ]

        # Execute tasks in parallel
        job = group(extraction_tasks)
        result = job.apply_async()

        # Schedule cleanup after tasks complete
        # Use countdown to ensure all extraction tasks finish
        cleanup_nwps_file.apply_async(
            args=[file_key],
            countdown=1800  # 30 min buffer
        )

        return {
            "status": "success",
            "region": region,
            "model_run": model_run.isoformat(),
            "file_size_mb": round(file_size_mb, 2),
            "spots_queued": len(spots),
            "file_key": file_key
        }

    def _get_provider(self, region: str) -> NWPSProvider:
        """Initialize NWPS provider for region"""
        # Load region config
        from services.forecast.providers.nwps_provider import NWPS_REGIONS
        return NWPSProvider(
            region_config=NWPS_REGIONS[region],
            http_client=self.http_manager.client
        )

    async def _get_spots_in_region(self, region: str) -> list:
        """Get all active spots in region from database"""
        async with self.db_manager.get_session() as session:
            from models.spot import Spot
            from sqlalchemy import select

            result = await session.execute(
                select(Spot).where(
                    Spot.active == True,
                    Spot.region == region.title()
                )
            )
            return result.scalars().all()


@shared_task(
    bind=True,
    base=AsyncTask,
    max_retries=2,
)
class ExtractNWPSSpotDataTask(AsyncTask):
    """
    Extract forecast data for a single spot from GRIB2 file.
    Lightweight task - many can run in parallel.
    """

    async def run_async(self, spot_id: str, file_key: str, region: str):
        # Get file metadata from Redis
        file_info = await self.redis_manager.hgetall(file_key)

        if not file_info:
            raise ValueError(f"File metadata not found: {file_key}")

        file_path = Path(file_info["file_path"])

        if not file_path.exists():
            raise FileNotFoundError(f"GRIB2 file not found: {file_path}")

        # Load spot from DB
        spot = await self._get_spot(spot_id)

        # Initialize provider
        provider = self._get_provider(region)

        # Extract forecast data
        # Note: This opens the file, but pygrib is efficient
        # Multiple tasks can read same file simultaneously
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=5)

        forecasts = await provider.extract_spot_forecasts(
            data_file=file_path,
            spots=[spot],
            start=start,
            end=end
        )

        spot_forecasts = forecasts.get(spot_id, [])

        # Store in Redis (existing hash pattern)
        stored_hours = 0
        for forecast_data in spot_forecasts:
            hour = forecast_data.timestamp.replace(minute=0, second=0, microsecond=0)
            redis_key = f"forecast:{spot_id}:{hour.isoformat()}"

            # Store wave data
            await self.redis_manager.hset(
                redis_key,
                "nwps:wave",
                json.dumps({
                    "height": forecast_data.wave_height,
                    "period": forecast_data.wave_period,
                    "direction": forecast_data.wave_direction,
                })
            )

            # Store wind data
            await self.redis_manager.hset(
                redis_key,
                "nwps:wind",
                json.dumps({
                    "speed": forecast_data.wind_speed,
                    "direction": forecast_data.wind_direction,
                })
            )

            # Store water level (tide+surge+setup)
            await self.redis_manager.hset(
                redis_key,
                "nwps:water_level",
                json.dumps({
                    "height": forecast_data.water_level,
                    "type": "total",  # tide + surge + wave setup
                })
            )

            # Metadata
            await self.redis_manager.hset(
                redis_key,
                "nwps:wave:updated_at",
                datetime.utcnow().isoformat()
            )

            # TTL: 14 hours (covers 12hr gap + buffer)
            await self.redis_manager.expire(redis_key, 50400)

            stored_hours += 1

        self.logger.info(f"Stored {stored_hours} forecast hours for spot {spot_id}")

        return {
            "spot_id": spot_id,
            "hours_stored": stored_hours
        }

    async def _get_spot(self, spot_id: str):
        """Load spot from database"""
        async with self.db_manager.get_session() as session:
            from models.spot import Spot
            spot = await session.get(Spot, spot_id)
            if not spot:
                raise ValueError(f"Spot not found: {spot_id}")
            return spot

    def _get_provider(self, region: str) -> NWPSProvider:
        """Initialize NWPS provider"""
        from services.forecast.providers.nwps_provider import NWPS_REGIONS
        return NWPSProvider(
            region_config=NWPS_REGIONS[region],
            http_client=self.http_manager.client
        )


@shared_task(bind=True, base=AsyncTask)
class CleanupNWPSFileTask(AsyncTask):
    """
    Cleanup GRIB2 file after all extraction tasks complete.
    """

    async def run_async(self, file_key: str):
        # Get file metadata
        file_info = await self.redis_manager.hgetall(file_key)

        if not file_info:
            self.logger.warning(f"File metadata already deleted: {file_key}")
            return {"status": "already_cleaned"}

        file_path = Path(file_info["file_path"])

        # Delete file
        if file_path.exists():
            file_path.unlink()
            self.logger.info(f"Deleted GRIB2 file: {file_path}")

        # Delete metadata from Redis
        await self.redis_manager.delete(file_key)

        return {"status": "cleaned", "file_path": str(file_path)}
```

### Celery Beat Schedule

```python
# backend/celery_app/app.py
from celery.schedules import crontab

app.conf.beat_schedule = {
    # NWPS runs at 00Z and 12Z
    # Add 30min delay for NOAA processing time
    'fetch-nwps-hawaii-00z': {
        'task': 'celery_app.tasks.nwps.fetch_nwps_regional',
        'schedule': crontab(hour=0, minute=30),  # 00:30 UTC
        'kwargs': {'region': 'hawaii'}
    },
    'fetch-nwps-hawaii-12z': {
        'task': 'celery_app.tasks.nwps.fetch_nwps_regional',
        'schedule': crontab(hour=12, minute=30),  # 12:30 UTC
        'kwargs': {'region': 'hawaii'}
    },
}
```

### Configuration

```python
# backend/services/forecast/providers/nwps_config.py

NWPS_REGIONS = {
    "hawaii": {
        "code": "CG4",
        "name": "Hawaii",
        "base_url": "https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod",
        "coverage": {
            "lat_min": 18.5,
            "lat_max": 22.5,
            "lon_min": -161.0,
            "lon_max": -154.5,
        },
        "model_runs": [0, 12],  # UTC hours
    },
    # Future regions:
    # "california": {...},
    # "east_coast": {...},
}
```

### Key Architectural Decisions

**1. File Persistence Strategy: Keep Until All Spots Processed** ✅
- **Why:** Simpler than Redis grid caching
- GRIB2 file stays in `/tmp` during extraction (10-20 min)
- Each extraction task opens file independently (pygrib is efficient)
- Cleanup task deletes file after buffer period

**2. Task Coordination via Redis Metadata**
- Store file location + metadata in Redis
- Each extraction task reads file path from Redis
- Prevents race conditions

**3. HTTP Client Still Needed**
- Even file-based providers need HTTP for downloading
- Streaming download handles 62MB efficiently
- Shared `http_manager` from WorkerState

**4. Dual-Mode Provider Protocol**
- `PerSpotProvider`: Traditional HTTP APIs (Surfline, etc.)
- `RegionalProvider`: File-based (NWPS, NetCDF)
- Both store to same Redis hash structure

**5. Error Handling**
- If extraction task fails for one spot, others continue
- Cleanup task uses countdown buffer (30 min)
- File metadata has TTL (prevents orphaned files)

### Integration with Existing Registry

```python
# backend/services/forecast/registry.py

class ForecastRegistry:
    """Enhanced registry supporting both processing modes"""

    def __init__(self):
        self._per_spot_providers: dict[str, PerSpotProvider] = {}
        self._regional_providers: dict[str, RegionalProvider] = {}
        self._spot_providers: dict[str, list[str]] = {}  # spot → provider names

    def register_per_spot_provider(self, name: str, provider: PerSpotProvider):
        """Register HTTP-based provider (Surfline, Open-Meteo, etc.)"""
        self._per_spot_providers[name] = provider

    def register_regional_provider(self, name: str, provider: RegionalProvider):
        """Register file-based provider (NWPS, PacIOOS NetCDF)"""
        self._regional_providers[name] = provider

    def get_regional_providers_for_region(self, region: str) -> list[RegionalProvider]:
        """Get all regional providers covering a region"""
        return [
            provider for provider in self._regional_providers.values()
            if provider.region == region
        ]

# Usage:
registry = ForecastRegistry()

# HTTP-based providers (per-spot fetching)
registry.register_per_spot_provider("surfline", SurflineProvider())
registry.register_per_spot_provider("open_meteo", OpenMeteoProvider())

# File-based providers (regional processing)
registry.register_regional_provider(
    "nwps",
    NWPSProvider(region_config=NWPS_REGIONS["hawaii"], http_client=...)
)
```

### Next Steps for Implementation

**Phase 1: Core NWPS Provider** (Start Here)
1. Implement `NWPSProvider` class with GRIB2 extraction
2. Test with single spot extraction
3. Verify data quality (compare with NOAA website)

**Phase 2: Task Orchestration**
1. Implement `FetchNWPSRegionalTask` (download + orchestration)
2. Implement `ExtractNWPSSpotDataTask` (per-spot extraction)
3. Implement `CleanupNWPSFileTask` (file deletion)
4. Test with 2-3 spots

**Phase 3: Production**
1. Add to Celery Beat schedule (00:30Z, 12:30Z)
2. Test with all 20 Maui spots
3. Monitor file download times, extraction performance
4. Add error handling + retry logic

**Phase 4: Scale**
1. Add more regions (Oahu, California, etc.)
2. Optimize GRIB2 extraction (bilinear interpolation, caching)
3. Consider multi-region orchestration

### Performance Expectations (Your Optiplex)

**Per Model Run (2x/day):**
- Download: 62MB in 5-20 sec (depending on connection)
- Extraction: 20 spots × 62 hours = ~1240 data points
  - GRIB2 read: ~5-10 sec per spot (can be optimized)
  - Total extraction time: 2-5 min (parallelized across workers)
- Storage: ~500KB in Redis (extracted data only)
- Cleanup: Instant

**Total resource impact:**
- Network: 124MB/day (negligible)
- Disk: 62MB temporary (deleted after ~20 min)
- CPU: ~2-5 min of processing 2x/day
- RAM: ~150MB peak during GRIB2 processing per worker

✅ **Completely reasonable for your setup!**
