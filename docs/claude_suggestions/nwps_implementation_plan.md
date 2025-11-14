# NWPS Forecast Service Implementation Plan

## Overview
Build core forecast service protocols and NWPS GRIB2 provider that fetches regional data and caches in Redis, with location-based provider registration.

---

## Phase 1: Core Foundation

### 1.1 Base Protocols & Models (`services/forecast/base.py`)

Define the core data structures and interfaces that all providers will implement.

```python
# backend/services/forecast/base.py
from typing import Protocol, runtime_checkable, Literal
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel


class ForecastData(BaseModel):
    """Unified forecast data model across all providers"""
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
        """Unique identifier for this provider (e.g., 'nwps', 'surfline')"""
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

    def is_available_for_spot(self, spot: "SurfSpot") -> bool:
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
        spot: "SurfSpot",
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
        """Geographic region this provider covers (e.g., "maui", "oahu")"""
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
        spots: list["SurfSpot"],
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

**Key Concepts:**
- **ForecastData**: Common format for all providers (wave/wind/water level)
- **ForecastProvider**: Base protocol with common properties
- **PerSpotProvider**: For future HTTP-based providers (Surfline, etc.)
- **RegionalProvider**: For GRIB2/file-based providers (NWPS)

---

### 1.2 Provider Registry (`services/forecast/registry.py`)

Registry pattern that manages provider instances and auto-registers based on LOCATION env.

```python
# backend/services/forecast/registry.py
from typing import Dict, List
from services.forecast.base import ForecastProvider, PerSpotProvider, RegionalProvider
import logging


class ForecastRegistry:
    """Registry for managing forecast providers with location-aware registration"""

    def __init__(self):
        self._per_spot_providers: Dict[str, PerSpotProvider] = {}
        self._regional_providers: Dict[str, RegionalProvider] = {}
        self.logger = logging.getLogger(__name__)

    def register_per_spot_provider(
        self,
        name: str,
        provider: PerSpotProvider
    ) -> None:
        """Register HTTP-based provider (Surfline, Open-Meteo, etc.)"""
        self._per_spot_providers[name] = provider
        self.logger.info(f"Registered per-spot provider: {name}")

    def register_regional_provider(
        self,
        name: str,
        provider: RegionalProvider
    ) -> None:
        """Register file-based provider (NWPS, PacIOOS NetCDF)"""
        self._regional_providers[name] = provider
        self.logger.info(f"Registered regional provider: {name} for region: {provider.region}")

    def get_regional_providers_for_region(
        self,
        region: str
    ) -> List[RegionalProvider]:
        """Get all regional providers covering a region"""
        return [
            provider for provider in self._regional_providers.values()
            if provider.region == region
        ]

    def get_provider_by_name(self, name: str) -> ForecastProvider | None:
        """Get any provider by name"""
        if name in self._per_spot_providers:
            return self._per_spot_providers[name]
        if name in self._regional_providers:
            return self._regional_providers[name]
        return None


# Module-level singleton
_registry: ForecastRegistry | None = None


def get_registry() -> ForecastRegistry:
    """Get or create the global forecast registry"""
    global _registry
    if _registry is None:
        _registry = ForecastRegistry()
        _initialize_providers(_registry)
    return _registry


def _initialize_providers(registry: ForecastRegistry) -> None:
    """
    Auto-register providers based on LOCATION env variable.
    Called once when registry is first accessed.
    """
    import os
    from services.forecast.providers.nwps_config import NWPS_REGIONS
    from services.forecast.providers.nwps_provider import NWPSProvider
    from core.http import AsyncHTTPManager

    location = os.getenv("LOCATION", "maui").lower()

    # Register NWPS provider for current location
    if location in NWPS_REGIONS:
        http_manager = AsyncHTTPManager()  # TODO: Get from WorkerState in production
        nwps_provider = NWPSProvider(
            region_config=NWPS_REGIONS[location],
            http_client=http_manager.client
        )
        registry.register_regional_provider("nwps", nwps_provider)

    # Future: Register other providers (Surfline, Open-Meteo, etc.)
```

**Key Concepts:**
- **Singleton Pattern**: One registry per application lifecycle
- **Location-Aware**: Auto-registers NWPS provider based on LOCATION env
- **Extensible**: Easy to add new providers (Surfline, etc.) later

---

### 1.3 Location Configuration (`services/forecast/providers/nwps_config.py`)

Move NWPS-specific location config from core/configs to forecast providers folder.

```python
# backend/services/forecast/providers/nwps_config.py
"""
NWPS (Nearshore Wave Prediction System) configuration per location.
Defines GRIB2 URLs, coverage areas, and model run times.
"""

NWPS_REGIONS = {
    "maui": {
        "code": "CG4",  # Coastal Grid 4
        "name": "Maui",
        "site_code": "HFO",  # Honolulu Forecast Office
        "base_url": "https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod",
        "coverage": {
            "lat_min": 20.5,
            "lat_max": 21.2,
            "lon_min": -156.7,
            "lon_max": -155.9,
        },
        "model_runs": [0, 12],  # UTC hours (00Z and 12Z)
        "forecast_hours": 144,  # 6 days
    },
    "oahu": {
        "code": "CG4",  # Same grid covers Oahu
        "name": "Oahu",
        "site_code": "HFO",
        "base_url": "https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod",
        "coverage": {
            "lat_min": 21.2,
            "lat_max": 21.7,
            "lon_min": -158.3,
            "lon_max": -157.6,
        },
        "model_runs": [0, 12],
        "forecast_hours": 144,
    },
}


def get_nwps_grib_url(region: str, model_run: datetime) -> str:
    """
    Build GRIB2 download URL for a specific region and model run.

    Example URL:
    https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwps/prod/nwps.20251113/CG4/nwps.t00z.cg4.grib2
    """
    config = NWPS_REGIONS[region]
    run_date = model_run.strftime("%Y%m%d")
    model_hour = model_run.hour  # 0 or 12

    code = config["code"]
    url = (
        f"{config['base_url']}/nwps.{run_date}/"
        f"{code}/nwps.t{model_hour:02d}z.{code.lower()}.grib2"
    )
    return url
```

**Key Concepts:**
- **Per-Location Config**: Each location has GRIB URLs, coverage areas
- **URL Builder**: Helper function to construct GRIB2 download URLs
- **Extensible**: Easy to add new regions (California, East Coast, etc.)

---

## Phase 2: NWPS Provider (Core Implementation)

### 2.1 NWPS Provider Class (`services/forecast/providers/nwps_provider.py`)

Implements RegionalProvider protocol with GRIB2 extraction logic.

```python
# backend/services/forecast/providers/nwps_provider.py
from services.forecast.base import RegionalProvider, ForecastData
from pathlib import Path
from datetime import datetime, timezone
import pygrib
import httpx
from typing import Literal
import logging


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
            region_config: Configuration dict from nwps_config.NWPS_REGIONS
            http_client: Shared HTTP client for downloads (from WorkerState)
        """
        self.region_config = region_config
        self.http_client = http_client
        self.logger = logging.getLogger(__name__)

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
        from services.forecast.providers.nwps_config import get_nwps_grib_url

        url = get_nwps_grib_url(self.region, model_run)

        # Download to temp location
        run_date = model_run.strftime("%Y%m%d")
        code = self.region_config["code"]
        output_file = Path(f"/tmp/nwps_{run_date}_{model_run.hour:02d}z_{code.lower()}.grib2")

        self.logger.info(f"Downloading GRIB2: {url}")

        # Streaming download (efficient for 62MB file)
        async with self.http_client.stream("GET", url) as response:
            response.raise_for_status()

            with open(output_file, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

        file_size_mb = output_file.stat().st_size / (1024 * 1024)
        self.logger.info(f"Downloaded {file_size_mb:.2f} MB to {output_file}")

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
                        spot.geometry.y,  # PostGIS Point latitude
                        spot.geometry.x   # PostGIS Point longitude
                    ),
                    wave_period=self._extract_value(
                        index.get("wave_period", {}).get(forecast_hour),
                        spot.geometry.y,
                        spot.geometry.x
                    ),
                    wave_direction=self._extract_value(
                        index.get("wave_direction", {}).get(forecast_hour),
                        spot.geometry.y,
                        spot.geometry.x
                    ),
                    wind_speed=self._extract_value(
                        index.get("wind_speed", {}).get(forecast_hour),
                        spot.geometry.y,
                        spot.geometry.x
                    ),
                    wind_direction=self._extract_value(
                        index.get("wind_direction", {}).get(forecast_hour),
                        spot.geometry.y,
                        spot.geometry.x
                    ),
                    water_level=self._extract_value(
                        index.get("water_level", {}).get(forecast_hour),
                        spot.geometry.y,
                        spot.geometry.x
                    ),
                )

                timeseries.append(forecast_data)

            results[str(spot.id)] = timeseries

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
            self.logger.warning(f"Failed to extract value at ({lat}, {lon}): {e}")
            return None
```

**Key Concepts:**
- **Streaming Download**: Efficient handling of 62MB GRIB2 files
- **GRIB Indexing**: Build in-memory index for fast lookup
- **Nearest Neighbor**: Extract point data at spot lat/lon
- **Error Handling**: Graceful degradation if extraction fails

---

## Phase 3: Celery Tasks (Orchestration)

### 3.1 Task Base Class (`tasks/base.py`)

Base class that enables async tasks with access to WorkerState resources.

```python
# backend/tasks/base.py
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

**Key Concepts:**
- **Async Support**: Run async code in Celery tasks
- **Resource Access**: Easy access to DB, Redis, HTTP managers
- **Reusable**: All forecast tasks extend this base class

---

### 3.2 NWPS Tasks (`tasks/nwps.py`)

Three tasks: Download → Extract → Cleanup

```python
# backend/tasks/nwps.py
from celery import shared_task, group
from tasks.base import AsyncTask
from services.forecast.registry import get_registry
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
    4. Schedule cleanup
    """

    async def run_async(self, region: str = "maui"):
        self.logger.info(f"Starting NWPS fetch for region: {region}")

        # Determine current model run (00Z or 12Z)
        now = datetime.now(timezone.utc)
        model_hour = 0 if now.hour < 12 else 12
        model_run = now.replace(hour=model_hour, minute=0, second=0, microsecond=0)

        # Get NWPS provider from registry
        registry = get_registry()
        provider = registry.get_provider_by_name("nwps")

        if not provider:
            raise ValueError("NWPS provider not registered")

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
        extraction_tasks = [
            extract_nwps_spot_data.s(
                spot_id=str(spot.id),
                file_key=file_key,
                region=region
            )
            for spot in spots
        ]

        # Execute tasks in parallel
        job = group(extraction_tasks)
        result = job.apply_async()

        # Schedule cleanup after tasks complete
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

    async def _get_spots_in_region(self, region: str) -> list:
        """Get all active spots in region from database"""
        async with self.db_manager.get_session() as session:
            from models.surf_spot_model import SurfSpot
            from sqlalchemy import select

            # Simple query - adjust based on your SurfSpot model
            result = await session.execute(
                select(SurfSpot).where(SurfSpot.active == True)
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

        # Get provider from registry
        from services.forecast.registry import get_registry
        registry = get_registry()
        provider = registry.get_provider_by_name("nwps")

        # Extract forecast data
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=5)

        forecasts = await provider.extract_spot_forecasts(
            data_file=file_path,
            spots=[spot],
            start=start,
            end=end
        )

        spot_forecasts = forecasts.get(spot_id, [])

        # Store in Redis (hash format)
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
            from models.surf_spot_model import SurfSpot
            spot = await session.get(SurfSpot, spot_id)
            if not spot:
                raise ValueError(f"Spot not found: {spot_id}")
            return spot


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


# Task name exports for celery autodiscovery
fetch_nwps_regional = FetchNWPSRegionalTask()
extract_nwps_spot_data = ExtractNWPSSpotDataTask()
cleanup_nwps_file = CleanupNWPSFileTask()
```

**Key Concepts:**
- **Orchestration**: Main task downloads GRIB2, fans out extraction
- **Parallel Extraction**: Each spot processed independently
- **Coordination via Redis**: File metadata stored for task communication
- **Cleanup**: Scheduled with countdown buffer to ensure extraction completes

---

### 3.3 Redis Cache Format

Example of what gets stored in Redis:

```
Key: forecast:550e8400-e29b-41d4-a716-446655440000:2025-11-13T12:00:00

Hash Fields:
├─ nwps:wave → '{"height": 4.5, "period": 12, "direction": 270}'
├─ nwps:wind → '{"speed": 15, "direction": 90}'
├─ nwps:water_level → '{"height": 1.2, "type": "total"}'
└─ nwps:wave:updated_at → "2025-11-13T12:05:32Z"

TTL: 50400 seconds (14 hours)
```

**Benefits:**
- One key per spot/hour
- Atomic updates (HSET operations)
- Easy retrieval (HGETALL for all data, HGET for specific provider)
- Single TTL per forecast hour

---

## Phase 4: Integration & Testing

### 4.1 Dependency Installation

Add pygrib to your dependencies:

```toml
# backend/pyproject.toml
[project]
dependencies = [
    # ... existing dependencies ...
    "pygrib>=2.1.4",
]
```

Install with:
```bash
cd backend
uv add pygrib
```

---

### 4.2 Manual Testing

Test the implementation step-by-step:

```python
# Test script: backend/scripts/test_nwps.py
import asyncio
from datetime import datetime, timezone
from services.forecast.registry import get_registry
from core.database import AsyncDatabaseManager
from core import get_settings


async def test_nwps():
    """Test NWPS provider end-to-end"""

    # Get provider from registry
    registry = get_registry()
    provider = registry.get_provider_by_name("nwps")

    print(f"Provider: {provider.provider_name}")
    print(f"Region: {provider.region}")
    print(f"Update frequency: {provider.update_frequency_seconds}s")

    # Determine current model run
    now = datetime.now(timezone.utc)
    model_hour = 0 if now.hour < 12 else 12
    model_run = now.replace(hour=model_hour, minute=0, second=0, microsecond=0)

    print(f"\nModel run: {model_run}")

    # Download GRIB2 file
    print("\nDownloading GRIB2 file...")
    grib_file = await provider.fetch_regional_data(model_run)
    print(f"Downloaded to: {grib_file}")

    # Get a test spot from database
    settings = get_settings()
    db_manager = AsyncDatabaseManager(settings.db)
    async with db_manager.get_session() as session:
        from models.surf_spot_model import SurfSpot
        from sqlalchemy import select

        result = await session.execute(select(SurfSpot).limit(1))
        test_spot = result.scalars().first()

    if not test_spot:
        print("No spots found in database")
        return

    print(f"\nTest spot: {test_spot.name} ({test_spot.geometry.y}, {test_spot.geometry.x})")

    # Extract forecasts
    print("\nExtracting forecasts...")
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=1)

    forecasts = await provider.extract_spot_forecasts(
        data_file=grib_file,
        spots=[test_spot],
        start=start,
        end=end
    )

    spot_forecasts = forecasts.get(str(test_spot.id), [])
    print(f"\nExtracted {len(spot_forecasts)} forecast hours")

    # Show first 3 forecasts
    for forecast in spot_forecasts[:3]:
        print(f"\n{forecast.timestamp}:")
        print(f"  Wave: {forecast.wave_height}m @ {forecast.wave_period}s from {forecast.wave_direction}°")
        print(f"  Wind: {forecast.wind_speed}m/s from {forecast.wind_direction}°")
        print(f"  Water Level: {forecast.water_level}m")

    # Cleanup
    grib_file.unlink()
    print(f"\nCleaned up GRIB2 file")


if __name__ == "__main__":
    asyncio.run(test_nwps())
```

Run with:
```bash
cd backend
python -m scripts.test_nwps
```

---

### 4.3 Celery Task Testing

Test the full Celery task orchestration:

```bash
# Terminal 1: Start Celery worker
cd backend
celery -A celery_app.app worker -l info

# Terminal 2: Trigger task manually
python -c "from tasks.nwps import fetch_nwps_regional; fetch_nwps_regional.delay('maui')"
```

Check Redis for cached data:
```bash
redis-cli
> KEYS forecast:*
> HGETALL forecast:550e8400-e29b-41d4-a716-446655440000:2025-11-13T12:00:00
```

---

### 4.4 Celery Beat Schedule (Future)

Add to Celery app config for automated scheduling:

```python
# backend/celery_app/app.py
from celery.schedules import crontab

app.conf.beat_schedule = {
    # NWPS runs at 00Z and 12Z
    # Add 30min delay for NOAA processing time
    'fetch-nwps-maui-00z': {
        'task': 'tasks.nwps.fetch_nwps_regional',
        'schedule': crontab(hour=0, minute=30),  # 00:30 UTC
        'kwargs': {'region': 'maui'}
    },
    'fetch-nwps-maui-12z': {
        'task': 'tasks.nwps.fetch_nwps_regional',
        'schedule': crontab(hour=12, minute=30),  # 12:30 UTC
        'kwargs': {'region': 'maui'}
    },
}
```

---

## Implementation Order

Follow this sequence for minimal friction:

1. **Base protocols** (`base.py`) - Foundation for everything
2. **NWPS config** (`nwps_config.py`) - Defines GRIB URLs per location
3. **Registry** (`registry.py`) - Manages provider instances
4. **NWPS provider** (`nwps_provider.py`) - GRIB2 extraction logic
5. **AsyncTask base** (`tasks/base.py`) - Task foundation
6. **NWPS tasks** (`tasks/nwps.py`) - Orchestration logic
7. **Test script** - Validate provider works
8. **Manual Celery test** - Validate tasks work
9. **Beat schedule** - Automate (once confident)

---

## Files to Create/Modify

### Create:
- `services/forecast/providers/nwps_config.py` - NWPS location config
- `services/forecast/providers/nwps_provider.py` - NWPS provider implementation
- `tasks/__init__.py` - Tasks package
- `tasks/base.py` - AsyncTask base class
- `tasks/nwps.py` - NWPS orchestration tasks
- `scripts/test_nwps.py` - Test script

### Modify:
- `services/forecast/base.py` - Add protocols and ForecastData model (currently empty)
- `services/forecast/registry.py` - Add ForecastRegistry class (currently empty)
- `pyproject.toml` - Add pygrib dependency

### Optional Cleanup:
- Consider removing/deprecating `core/configs/location_config.py` (NWPS config now in providers)

---

## Key Design Decisions

1. **Location Config Placement**: Move from `core/configs` to `services/forecast/providers` since it's NWPS-specific
2. **Provider Registration**: Registry auto-registers based on LOCATION env variable
3. **Storage Strategy**: Redis cache only (no database persistence)
4. **Scope**: Core protocols + NWPS provider that caches data (API endpoint deferred)
5. **GRIB Processing**: Download → extract for all spots → cache → cleanup file
6. **Task Pattern**: Three-task orchestration (fetch → extract → cleanup)
7. **Error Handling**: Per-spot extraction failures don't block other spots

---

## Performance Expectations

**Per Model Run (2x/day):**
- Download: 62MB in 5-20 sec
- Extraction: ~20 spots × 144 hours = ~2880 data points
  - GRIB2 read: ~5-10 sec per spot
  - Total extraction: 2-5 min (parallelized)
- Storage: ~500KB in Redis (JSON data only)
- Cleanup: Instant

**Resource Impact:**
- Network: 124MB/day
- Disk: 62MB temporary (deleted after ~30 min)
- CPU: ~2-5 min processing 2x/day
- RAM: ~150MB peak during GRIB2 processing per worker

✅ **Well within your Optiplex 7050 capabilities!**

---

## Next Steps After Implementation

Once this foundation is working:

1. **Add API endpoint** to retrieve cached forecasts
2. **Implement Surfline provider** (PerSpotProvider example)
3. **Add Open-Meteo provider** (another HTTP API)
4. **Implement provider priority/fallback** logic
5. **Add monitoring/alerting** for failed tasks
6. **Optimize GRIB extraction** (bilinear interpolation, caching)
7. **Scale to more regions** (Oahu, California, etc.)

---

## Questions to Consider

1. **Spot Model**: Does your `SurfSpot` model have `active` field for filtering?
2. **Region Filtering**: How should tasks filter spots by region? (geometry check, or explicit region field?)
3. **HTTP Manager**: Should registry use WorkerState's HTTP manager or create its own?
4. **Error Notifications**: Want Slack/email alerts for failed GRIB downloads?
5. **Data Validation**: Should we validate extracted values (e.g., wave height < 30m)?

---

This plan provides a solid foundation for building out your forecast service layer! Start small with the base protocols, then implement NWPS step-by-step. Each phase builds on the previous, allowing you to test incrementally.
