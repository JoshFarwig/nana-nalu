# Forecast Service Implementation Plan

## Overview

Build a provider-agnostic forecast service supporting multiple providers:

- **File-Based Providers**: NWPS (GRIB2), PacIOOS GridDAP (NetCDF)
- **API-Based Providers**: Surfline (per-spot HTTP), Open-Meteo (batch HTTP)

Store raw provider data in Redis, transform into standardized views via API layer.

---

## Architecture Philosophy

### Data Storage: Raw Provider Format

**Store exactly what providers give you in Redis** - no normalization at cache layer.

```
Key: forecast:nwps:{spot_id}:{timestamp}
Value: {"swh": 4.5, "shts": 4.0, "perpw": 12, "dirpw": 270, ...}

Key: forecast:surfline:{spot_id}:{timestamp}
Value: {"surf_optimal": 14, "swell1_height": 12, "swell1_period": 13, ...}

Key: forecast:pacioos:{spot_id}:{timestamp}
Value: {"Hsig": 4.2, "Tm01": 11.5, "Pdir01": 285, ...}
```

**Benefits:**

- No data loss - preserve provider-specific parameters (NWPS currents, Surfline ratings)
- Easy to debug - inspect raw Redis values
- Provider evolution - add new parameters without migrating data
- Power users - can access raw data if needed

### API Layer: Standardized Views

**Transform on read** - backend generates UI-friendly views from raw data.

```python
GET /spots/{spot_id}/forecast/swell
→ Transforms raw NWPS + Surfline data into structured swell comparison

GET /spots/{spot_id}/forecast/wave-height
→ Returns nearshore wave height from both providers (handles units, terminology)

GET /spots/{spot_id}/forecast/raw?provider=nwps
→ Returns unmodified NWPS data for advanced users
```

**Benefits:**

- UI stays simple - gets pre-structured data
- Iterate on views - change presentation without re-fetching provider data
- Cross-provider queries - backend handles provider differences

---

## Phase 1: Core Foundation

### 1.1 Provider Protocols (`services/forecast/base.py`)

Define interfaces that all providers must implement using **Protocol** (structural typing).

**Why Protocol?**

- No inheritance required - classes just need matching attributes/methods
- Type checking without coupling
- Clean interface definitions

**Key Abstractions:**

- `ForecastProvider` - Base protocol (provider name, update frequency, coverage check)
- `FileBasedProvider` - Download regional files, extract for multiple spots
- `APIBasedProvider` - HTTP requests with optional batching

**FileBasedProvider Flow:**

1. Download regional file (e.g., 62MB GRIB2 or 50MB NetCDF)
2. Extract data for many spots from single file using xarray
3. Store extracted data in Redis
4. Clean up file after processing

**Examples:**

- NWPS: GRIB2 files with xarray + cfgrib
- PacIOOS GridDAP: NetCDF files with xarray (default engine)

**APIBasedProvider Flow:**

1. Make HTTP request(s) to provider API
2. Parse response (JSON, binary NetCDF, etc.)
3. Store raw provider data in Redis
4. No file cleanup needed (in-memory processing)

**Examples:**

- Surfline: Per-spot requests (`supports_batching=False`)
- Open-Meteo: Batch multiple lat/lons (`supports_batching=True`)
- PacIOOS NCSS: Per-spot NetCDF-3 binary (`supports_batching=False`)

### 1.2 Provider Registry (`services/forecast/registry.py`)

**Singleton pattern** - manages provider instances, auto-registers based on `LOCATION` env variable.

```python
# At application startup:
registry = get_registry()
# → Reads LOCATION env ("maui")
# → Auto-registers NWPSProvider with Maui config
# → Auto-registers SurflineProvider (if configured)

# In tasks/endpoints:
provider = registry.get_provider_by_name("nwps")
regional_providers = registry.get_regional_providers_for_region("maui")
```

**Location-Aware Registration:**

- `LOCATION=maui` → Register NWPS with CG4 grid config
- `LOCATION=oahu` → Register NWPS with different coverage area
- Future: `LOCATION=california` → Register different regional models

### 1.3 NWPS Configuration (`services/forecast/providers/nwps_config.py`)

**Per-region GRIB2 configuration:**

- Grid code (e.g., CG4 for Hawaii)
- Coverage area (lat/lon bounds)
- Model run times (00Z, 12Z)
- Base URL for NOAA NOMADS server

**Example:**

```python
NWPS_REGIONS = {
    "maui": {
        "code": "CG4",
        "coverage": {"lat_min": 20.5, "lat_max": 21.2, ...},
        "model_runs": [0, 12],  # UTC hours
        ...
    }
}
```

**Why separate file?**

- Location configs are NWPS-specific, not global
- Easy to add new regions without touching provider code
- Keeps `core/configs` for app-wide settings

---

## Phase 2: File-Based Providers

### 2.1 NWPS Provider (`services/forecast/providers/nwps_provider.py`)

**Implements FileBasedProvider protocol** - processes GRIB2 files with xarray + cfgrib.

**Key Responsibilities:**

1. **Download GRIB2 file** (62MB, ~5-20 sec)
2. **Extract point data** using xarray + cfgrib (lazy loading, efficient)
3. **Return raw parameter names** - preserve NOAA's native format

**xarray vs pygrib:**

- ✅ xarray: Cleaner API, lazy loading, easy lat/lon selection
- ❌ pygrib: More boilerplate, loads entire file into memory

**Example extraction:**

```python
ds = xr.open_dataset(grib_file, engine='cfgrib', filter_by_keys={'dataType': 'fc'})
spot_data = ds.sel(latitude=20.93, longitude=203.64, method='nearest')

# Return raw GRIB variable names
return {
    "swh": float(spot_data["swh"].values[0]),  # Significant wave height
    "shts": float(spot_data["shts"].values[0]),  # Swell height (no wind waves)
    "perpw": float(spot_data["perpw"].values[0]),  # Period
    "dirpw": float(spot_data["dirpw"].values[0]),  # Direction
    "spc": float(spot_data["spc"].values[0]),  # Current speed (unique!)
    "dirc": float(spot_data["dirc"].values[0]),  # Current direction
    "zos": float(spot_data["zos"].values[0]),  # Water level (tide+surge+setup)
    ...
}
```

**GRIB2 Variable Reference:**

- `swh` - Significant wave height (total: swell + wind waves) - **nearshore height**
- `shts` - Significant height total swell (swell only) - **offshore swell component**
- `perpw` - Primary wave mean period
- `dirpw` - Primary wave direction
- `ws` - Wind speed
- `wdir` - Wind direction
- `spc` - Current speed (**NWPS exclusive**)
- `dirc` - Current direction (**NWPS exclusive**)
- `zos` - Sea surface height (**NWPS exclusive**: tide + storm surge + wave setup)

**Why these variables matter:**

- `swh` - What actually hits the beach (physics-based nearshore transformation)
- `shts` - Offshore swell (comparable to Surfline's deep-water swell)
- Currents - Safety + paddling effort (no other provider shows this!)
- Water level - Time your session (reef spots need depth)

### 2.2 NWPS Architecture Notes

**NWPS Model Components:**

- **Boundary conditions**: WAVEWATCH III (offshore waves)
- **Wind forcing**: AWIPS forecaster-developed grids (human-refined)
- **Wave model**: SWAN (nearshore transformation with bathymetry)
- **Currents**: RTOFS-Global (Real-Time Ocean Forecast System)
- **Water level**: ESTOFS (tides + surge) or P-SURGE (tropical storms)
- **Resolution**: 1.8km to 500m nearshore

**This is a physics-based model** - not statistical like most surf forecasts. It accounts for:

- Reef/bathymetry effects (wave shoaling, refraction)
- Wave-current interaction
- Local wind effects
- Total water level (critical for shallow reef spots)

### 2.3 PacIOOS GridDAP Provider (`services/forecast/providers/pacioos_griddap_provider.py`)

**Implements FileBasedProvider protocol** - processes NetCDF files from ERDDAP GridDAP service.

**Why GridDAP vs NCSS?**

- **GridDAP**: Download regional NetCDF grid covering many spots (file-based workflow)
- **NCSS**: Per-spot queries via HTTP API (API-based workflow)
- Use GridDAP when you have many spots in a region (more efficient)

**Key Responsibilities:**

1. **Download NetCDF file** from ERDDAP GridDAP (~20-50MB, depends on region/time range)
2. **Extract point data** using xarray (same as NWPS, but no cfgrib engine needed)
3. **Return raw PacIOOS variable names** - preserve native format

**Example extraction:**

```python
# Download NetCDF from GridDAP
url = "https://pae-paha.pacioos.hawaii.edu/erddap/griddap/swan_oahu.nc"
params = {
    "Hsig[(2025-11-14T00:00:00Z):1:(2025-11-20T00:00:00Z)][(20.5):(21.5)][(-158.5):(-157.5)]",
    "Tm01[(2025-11-14T00:00:00Z):1:(2025-11-20T00:00:00Z)][(20.5):(21.5)][(-158.5):(-157.5)]",
    ...
}

# Open with xarray (NetCDF is default engine)
ds = xr.open_dataset(nc_file)

# Extract point data (identical to NWPS workflow)
spot_data = ds.sel(latitude=20.93, longitude=-157.86, method='nearest')

# Return raw PacIOOS variable names
return {
    "Hsig": spot_data["Hsig"].values.tolist(),  # Significant wave height
    "Tm01": spot_data["Tm01"].values.tolist(),  # Mean period
    "Pdir01": spot_data["Pdir01"].values.tolist(),  # Primary direction
    "TPsmoo": spot_data["TPsmoo"].values.tolist(),  # Smoothed peak period
    "watlev": spot_data["watlev"].values.tolist(),  # Water level
    "times": [t.isoformat() for t in spot_data["time"].values],
    ...
}
```

**NetCDF Variable Reference (PacIOOS SWAN):**

- `Hsig` - Significant wave height (meters)
- `Tm01` - Mean wave period (seconds)
- `Pdir01` - Primary wave direction (degrees)
- `TPsmoo` - Smoothed peak period (seconds)
- `watlev` - Water level above MSL (meters)

**GRIB2 vs NetCDF Comparison:**

| Aspect | NWPS (GRIB2) | PacIOOS GridDAP (NetCDF) |
|--------|--------------|--------------------------|
| **Engine** | `engine='cfgrib'` | Default (native NetCDF) |
| **File size** | ~62MB | ~20-50MB (compressed) |
| **Variables** | GRIB abbreviations (`swh`, `perpw`) | Descriptive names (`Hsig`, `Tm01`) |
| **Workflow** | Identical | Identical |
| **xarray code** | Nearly identical | Nearly identical |

Both use the same `FileBasedProvider` workflow:

1. Download regional file
2. Extract with `ds.sel(latitude=..., longitude=..., method='nearest')`
3. Cache extracted data
4. Clean up file

---

## Phase 3: API-Based Providers

### 3.1 Surfline Provider (`services/forecast/providers/surfline_provider.py`)

**Implements APIBasedProvider protocol** - fetches via HTTP API (per-spot).

**Batch Request Strategy:**
Surfline doesn't have official batch API, but you can:

**Option A: Sequential requests with rate limiting**

```python
async def fetch_many(spots: list[SurfSpot]) -> dict[str, dict]:
    results = {}
    async with self.semaphore:  # Limit concurrent requests
        for spot in spots:
            if spot.surfline_spot_id:
                data = await self._fetch_single(spot.surfline_spot_id)
                results[str(spot.id)] = data
                await asyncio.sleep(0.1)  # Rate limit
    return results
```

**Option B: Gather with concurrency limit**

```python
semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests

async def fetch_with_limit(spot):
    async with semaphore:
        return await self._fetch_single(spot.surfline_spot_id)

tasks = [fetch_with_limit(spot) for spot in spots]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Return raw Surfline format:**

```python
{
    "surf_min": 12,
    "surf_max": 15,
    "surf_optimal": 14,
    "swell_height": 12,  # Offshore deep-water swell
    "swell_period": 13,
    "swell_direction": 265,
    "swell2_height": 3,  # Secondary swell
    "wind_speed": 10,
    "rating": 3,  # Stars
    "condition_human": "Fair - Bumpy",
    ...
}
```

**Surfline Data Characteristics:**

- Statistical model (buoy-calibrated)
- Offshore swell predictions (deep water, no nearshore transformation)
- `surf_optimal` is their guess at beach height
- Multiple swell components (primary, secondary, tertiary)
- Subjective ratings (★ stars, conditions text)

### 3.2 Batching Strategy for 200+ Spots

**Problem:** If you have 150 spots with Surfline data, sequential requests take ~15+ seconds.

**Solutions:**

**1. Smart Scheduling (Recommended)**
Don't fetch all spots every time:

```python
# Celery beat schedule
'fetch-surfline-priority-spots': {
    'schedule': crontab(minute='*/10'),  # Every 10 min
    'task': 'fetch_surfline_batch',
    'kwargs': {'priority': 'high'}  # Top 20 spots only
}

'fetch-surfline-all-spots': {
    'schedule': crontab(minute='0', hour='*/3'),  # Every 3 hours
    'task': 'fetch_surfline_batch',
    'kwargs': {'priority': 'all'}  # All 150 spots
}
```

**2. Concurrent Fetching with Throttling**

```python
# Fetch 10 spots at a time (1-2 seconds per batch)
async def fetch_surfline_batch(spots: list[SurfSpot]):
    semaphore = asyncio.Semaphore(10)
    tasks = [fetch_with_limit(spot, semaphore) for spot in spots]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 150 spots / 10 concurrent = 15 waves ≈ 15-30 seconds total
```

**3. Incremental Updates**

```python
# Only fetch spots with stale data
async def fetch_stale_spots():
    for spot in spots:
        last_update = await redis.get(f"forecast:surfline:{spot.id}:updated")
        if not last_update or (now - last_update) > timedelta(hours=1):
            await fetch_surfline(spot)
```

**4. User-Triggered Fetching**

```python
# When user views a spot, trigger fresh fetch if stale
@router.get("/spots/{spot_id}/forecast")
async def get_forecast(spot_id: str):
    # Return cached data immediately
    cached = await get_cached_forecast(spot_id)

    # Trigger background refresh if stale (fire-and-forget)
    if is_stale(cached):
        refresh_forecast_task.delay(spot_id)

    return cached
```

**Recommended Approach:** Combination of #1 + #2

- High-traffic spots: Fetch every 10 minutes (small batch)
- All spots: Fetch every 3-6 hours (large batch with throttling)
- On-demand: User views trigger background refresh if >1 hour old

**Network Load Estimation:**

- 150 spots × ~50KB response = ~7.5MB per full refresh
- Every 3 hours = 60MB/day (negligible)
- With smart scheduling (priority spots every 10min): ~100MB/day

### 3.2 Open-Meteo Provider (`services/forecast/providers/open_meteo_provider.py`)

**Implements APIBasedProvider protocol** - fetches via HTTP API with **batching support**.

**Key Feature: Batch Requests**
Open-Meteo supports multiple lat/lon pairs in a single request:

```python
class OpenMeteoProvider:
    provider_name = "open_meteo"
    processing_mode = "api_based"
    supports_batching = True  # Can batch multiple spots!
    update_frequency_hours = 1

    async def fetch_forecast(
        self, spots: list[SurfSpot], timestamp: datetime
    ) -> dict[str, dict]:
        # Batch all spots into one request
        lats = [str(spot.latitude) for spot in spots]
        lons = [str(spot.longitude) for spot in spots]

        url = "https://marine-api.open-meteo.com/v1/marine"
        params = {
            "latitude": ",".join(lats),
            "longitude": ",".join(lons),
            "hourly": "wave_height,wave_direction,wave_period,wind_wave_height",
            "timezone": "UTC",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()

        # Parse response into spot_id -> forecast dict
        results = {}
        for i, spot in enumerate(spots):
            results[str(spot.id)] = {
                "wave_height": data[i]["hourly"]["wave_height"],
                "wave_period": data[i]["hourly"]["wave_period"],
                "wave_direction": data[i]["hourly"]["wave_direction"],
                ...
            }

        return results
```

**Benefits of Open-Meteo:**

- ✅ Free, no API key required
- ✅ Batch 100+ locations in one request
- ✅ Hourly updates (vs Surfline's 3-6 hour delays)
- ✅ Global coverage
- ⚠️ Offshore forecast only (no nearshore transformation like NWPS)

---

## Phase 4: API View Layer

### 4.1 Forecast Views (`services/forecast/views.py`)

Transform raw provider data into UI-friendly formats.

**View Examples:**

```python
class ForecastViews:
    @staticmethod
    def get_swell_comparison(nwps_raw: dict, surfline_raw: dict) -> dict:
        """
        Standardize swell data across providers.
        NWPS: Single primary swell (shts, perpw, dirpw)
        Surfline: Multiple swells (swell1, swell2, swell3)
        """
        return {
            "nwps": [{
                "type": "primary",
                "height_m": nwps_raw["shts"],
                "period_s": nwps_raw["perpw"],
                "direction_deg": nwps_raw["dirpw"]
            }],
            "surfline": [
                {
                    "type": "primary",
                    "height_ft": surfline_raw["swell1_height"],
                    "period_s": surfline_raw["swell1_period"],
                    "direction_deg": surfline_raw["swell1_direction"]
                },
                {
                    "type": "secondary",
                    "height_ft": surfline_raw.get("swell2_height"),
                    ...
                }
            ]
        }

    @staticmethod
    def get_nearshore_wave_height(nwps_raw: dict, surfline_raw: dict) -> dict:
        """
        Compare predicted beach wave height.
        NWPS: Physics-based (swh = nearshore transformation)
        Surfline: Statistical estimate (surf_optimal)
        """
        return {
            "nwps": {
                "height_m": nwps_raw["swh"],
                "source": "SWAN physics model",
                "type": "nearshore_transformed"
            },
            "surfline": {
                "height_ft": surfline_raw["surf_optimal"],
                "height_range_ft": [
                    surfline_raw["surf_min"],
                    surfline_raw["surf_max"]
                ],
                "source": "statistical_model",
                "type": "estimated"
            }
        }

    @staticmethod
    def get_unique_to_provider(nwps_raw: dict, surfline_raw: dict) -> dict:
        """
        Highlight provider-exclusive data.
        """
        return {
            "nwps_exclusive": {
                "current_speed_ms": nwps_raw["spc"],
                "current_direction_deg": nwps_raw["dirc"],
                "water_level_m": nwps_raw["zos"],  # tide + surge + setup
                "components": "RTOFS currents + ESTOFS water level"
            },
            "surfline_exclusive": {
                "rating_stars": surfline_raw["rating"],
                "conditions_text": surfline_raw["condition_human"],
                "surf_range": [surfline_raw["surf_min"], surfline_raw["surf_max"]]
            }
        }
```

### 4.2 API Endpoints (`routers/forecast.py`)

```python
@router.get("/spots/{spot_id}/forecast")
async def get_spot_forecast(spot_id: str, timestamp: datetime | None = None):
    """
    Combined forecast view - all providers for a timestamp.
    Default: current time (nearest hour).
    """
    ts = timestamp or datetime.now(timezone.utc).replace(minute=0, second=0)

    # Fetch raw data from Redis
    nwps_raw = await redis.hgetall(f"forecast:nwps:{spot_id}:{ts.isoformat()}")
    surfline_raw = await redis.hgetall(f"forecast:surfline:{spot_id}:{ts.isoformat()}")

    # Generate views
    return {
        "timestamp": ts,
        "swell": ForecastViews.get_swell_comparison(nwps_raw, surfline_raw),
        "wave_height": ForecastViews.get_nearshore_wave_height(nwps_raw, surfline_raw),
        "wind": ForecastViews.get_wind_comparison(nwps_raw, surfline_raw),
        "unique_data": ForecastViews.get_unique_to_provider(nwps_raw, surfline_raw),
        "raw": {
            "nwps": nwps_raw,
            "surfline": surfline_raw
        }
    }

@router.get("/spots/{spot_id}/forecast/swell")
async def get_swell_forecast(spot_id: str):
    """Just swell data (6-day timeseries)."""
    ...

@router.get("/spots/{spot_id}/forecast/raw")
async def get_raw_forecast(spot_id: str, provider: str):
    """Power user endpoint - raw provider data."""
    ...
```

---

## Phase 5: Celery Tasks (Orchestration)

### 5.1 Task Base Class (`tasks/base.py`)

Simple async task wrapper with WorkerState access.

```python
class AsyncTask(Task):
    def __call__(self, *args, **kwargs):
        state = WorkerState()
        return state.loop.run_until_complete(self.run_async(*args, **kwargs))

    async def run_async(self, *args, **kwargs):
        raise NotImplementedError
```

### 5.2 File-Based Provider Tasks (`tasks/file_based.py`)

**Three-task orchestration pattern** - used by both NWPS and PacIOOS GridDAP:

**1. `FetchRegionalFileTask` (Orchestrator)**

- Download regional file (GRIB2 or NetCDF)
- Store file metadata in Redis (path, model run, size, provider)
- Query DB for all spots in region
- Fan out extraction tasks (one per spot)
- Schedule cleanup task (+30 min buffer)

**2. `ExtractSpotDataTask` (Worker)**

- Read file path and provider from Redis
- Load spot from DB
- Extract point data using xarray (with appropriate engine)
  - NWPS: `xr.open_dataset(path, engine='cfgrib')`
  - PacIOOS: `xr.open_dataset(path)`  # default NetCDF engine
- Store raw provider variables in Redis: `forecast:{provider}:{spot_id}:{timestamp}`
- Set TTL (provider-specific)

**3. `CleanupFileTask` (Cleanup)**

- Delete file from `/tmp`
- Delete file metadata from Redis

**Parallelization:**

- Main task: 1 (download)
- Extraction tasks: N (one per spot, run concurrently)
- Example: 20 spots × 5 sec = 100 sec total (vs 100 sec sequential)

**Provider-Specific Implementations:**

```python
# tasks/nwps.py
@shared_task(base=FetchRegionalFileTask)
def fetch_nwps(region: str):
    provider = registry.get_provider("nwps")
    # Uses provider.download_regional_file()
    ...

# tasks/pacioos.py
@shared_task(base=FetchRegionalFileTask)
def fetch_pacioos_griddap(region: str):
    provider = registry.get_provider("pacioos_griddap")
    # Uses provider.download_regional_file()
    ...
```

### 5.3 API-Based Provider Tasks (`tasks/api_based.py`)

**Single-task pattern** - simpler than file-based (no download/cleanup):

**`FetchAPIProviderTask`**

- Query DB for spots (filter by provider availability)
- Call provider's `fetch_forecast()` method
  - If `supports_batching=True`: One request for all spots (Open-Meteo)
  - If `supports_batching=False`: N requests with rate limiting (Surfline)
- Parse responses
- Store in Redis: `forecast:{provider}:{spot_id}:{timestamp}`
- Set TTL (provider-specific)

**Provider-Specific Implementations:**

```python
# tasks/surfline.py
@shared_task(base=FetchAPIProviderTask)
async def fetch_surfline_batch(priority: str = "all"):
    provider = registry.get_provider("surfline")
    spots = get_spots_for_priority(priority)

    # Surfline: supports_batching=False → sequential with rate limiting
    results = await provider.fetch_forecast(spots, datetime.now())
    await cache_results(results, provider_name="surfline")

# tasks/open_meteo.py
@shared_task(base=FetchAPIProviderTask)
async def fetch_open_meteo(region: str):
    provider = registry.get_provider("open_meteo")
    spots = get_spots_for_region(region)

    # Open-Meteo: supports_batching=True → single request for all spots
    results = await provider.fetch_forecast(spots, datetime.now())
    await cache_results(results, provider_name="open_meteo")
```

**Rate Limiting (for non-batching providers):**

```python
# Inside provider implementation
async def fetch_forecast(self, spots: list[SurfSpot], timestamp: datetime):
    if not self.supports_batching:
        # Use Redis-based rate limiter
        results = {}
        for spot in spots:
            # Check rate limit
            count = await redis.incr(f"{self.provider_name}:requests:minute")
            if count == 1:
                await redis.expire(f"{self.provider_name}:requests:minute", 60)
            if count > 60:
                await asyncio.sleep(1)

            # Fetch single spot
            results[str(spot.id)] = await self._fetch_single(spot)
        return results
    else:
        # Batch request
        return await self._fetch_batch(spots)
```

---

## Redis Storage Format

### Key Structure

```
forecast:{provider}:{spot_id}:{timestamp}
```

### NWPS Example

```
Key: forecast:nwps:550e8400-e29b-41d4-a716-446655440000:2025-11-14T12:00:00

Value (JSON string):
{
  "swh": 4.5,        // Total wave height (nearshore)
  "shts": 4.0,       // Swell height only (offshore)
  "perpw": 12,       // Period
  "dirpw": 270,      // Direction
  "ws": 15,          // Wind speed
  "wdir": 90,        // Wind direction
  "spc": 0.5,        // Current speed
  "dirc": 180,       // Current direction
  "zos": 1.2,        // Water level
  "updated_at": "2025-11-14T06:30:00Z",
  "model_run": "2025-11-14T00:00:00Z"
}

TTL: 50400 seconds (14 hours)
```

### Surfline Example

```
Key: forecast:surfline:550e8400-e29b-41d4-a716-446655440000:2025-11-14T12:00:00

Value (JSON string):
{
  "surf_min": 12,
  "surf_max": 15,
  "surf_optimal": 14,
  "swell1_height": 12,
  "swell1_period": 13,
  "swell1_direction": 265,
  "swell2_height": 3,
  "swell2_period": 8,
  "wind_speed": 10,
  "wind_direction": 85,
  "rating": 3,
  "condition_human": "Fair - Bumpy",
  "updated_at": "2025-11-14T06:00:00Z"
}

TTL: 21600 seconds (6 hours)
```

### PacIOOS GridDAP Example

```
Key: forecast:pacioos:550e8400-e29b-41d4-a716-446655440000:2025-11-14T12:00:00

Value (JSON string):
{
  "Hsig": [4.2, 4.3, 4.1, ...],  // 144 hourly values
  "Tm01": [11.5, 11.6, 11.4, ...],
  "Pdir01": [285, 286, 284, ...],
  "TPsmoo": [13.2, 13.3, 13.1, ...],
  "watlev": [0.3, 0.4, 0.2, ...],
  "times": ["2025-11-14T00:00:00Z", "2025-11-14T01:00:00Z", ...],
  "updated_at": "2025-11-14T06:30:00Z",
  "model_run": "2025-11-14T00:00:00Z"
}

TTL: 50400 seconds (14 hours)
```

### Open-Meteo Example

```
Key: forecast:open_meteo:550e8400-e29b-41d4-a716-446655440000:2025-11-14T12:00:00

Value (JSON string):
{
  "wave_height": [4.1, 4.2, 4.0, ...],
  "wave_period": [11.0, 11.2, 10.9, ...],
  "wave_direction": [280, 281, 279, ...],
  "wind_wave_height": [1.5, 1.6, 1.4, ...],
  "times": ["2025-11-14T00:00:00Z", ...],
  "updated_at": "2025-11-14T12:00:00Z"
}

TTL: 7200 seconds (2 hours)
```

**Why this format:**

- Simple key structure (easy to query all providers for a spot/time)
- Raw JSON preserves all provider fields
- Individual TTLs per forecast hour
- Can add new providers without migration (`forecast:open-meteo:...`)

---

## Implementation Order

**Phase 1: Foundation (Week 1)**

1. Create `services/forecast/base.py` - Protocol definitions
2. Create `services/forecast/registry.py` - Provider registry
3. Create `services/forecast/providers/nwps_config.py` - NWPS regions

**Phase 2: File-Based Providers (Week 1-2)**
4. Create `services/forecast/providers/nwps_provider.py` - GRIB2 extraction
5. Create `services/forecast/providers/pacioos_griddap_provider.py` - NetCDF extraction
6. Create test script `scripts/test_file_providers.py` - Validate both work
7. Install dependencies: `uv add xarray cfgrib netCDF4`

**Phase 3: Tasks (Week 2)**
8. Create `tasks/base.py` - AsyncTask base class
9. Create `tasks/file_based.py` - Shared file-based orchestration (3 tasks)
10. Create `tasks/nwps.py` - NWPS-specific task wrappers
11. Create `tasks/pacioos.py` - PacIOOS-specific task wrappers
12. Test Celery execution manually

**Phase 4: API Layer (Week 3)**
13. Create `services/forecast/views.py` - View transformations
14. Create `routers/forecast.py` - API endpoints
15. Test with Swagger UI

**Phase 5: API-Based Providers (Week 3-4)**
16. Create `services/forecast/providers/surfline_provider.py` - Per-spot HTTP
17. Create `services/forecast/providers/open_meteo_provider.py` - Batch HTTP
18. Create `tasks/api_based.py` - Shared API task orchestration
19. Create `tasks/surfline.py` - Surfline-specific wrappers
20. Create `tasks/open_meteo.py` - Open-Meteo-specific wrappers
21. Add to registry initialization

**Phase 6: Automation (Week 4)**
22. Add Celery Beat schedules:
    - NWPS: 2x/day (00Z, 12Z model runs)
    - PacIOOS GridDAP: 4x/day (every 6 hours)
    - Surfline: Priority spots every 10min, all spots every 3 hours
    - Open-Meteo: Every hour (free tier allows frequent updates)
23. Add monitoring/alerting

---

## Files to Create

**Core Services:**

- `backend/services/forecast/base.py` - Protocols (FileBasedProvider, APIBasedProvider)
- `backend/services/forecast/registry.py` - Provider registry
- `backend/services/forecast/views.py` - View transformations

**File-Based Providers:**

- `backend/services/forecast/providers/__init__.py`
- `backend/services/forecast/providers/nwps_config.py` - NWPS regional configs
- `backend/services/forecast/providers/nwps_provider.py` - GRIB2 extraction
- `backend/services/forecast/providers/pacioos_config.py` - PacIOOS regional configs
- `backend/services/forecast/providers/pacioos_griddap_provider.py` - NetCDF extraction

**API-Based Providers:**

- `backend/services/forecast/providers/surfline_provider.py` - Per-spot HTTP API
- `backend/services/forecast/providers/open_meteo_provider.py` - Batch HTTP API

**Tasks:**

- `backend/tasks/__init__.py`
- `backend/tasks/base.py` - AsyncTask base class
- `backend/tasks/file_based.py` - Shared file-based orchestration (download, extract, cleanup)
- `backend/tasks/nwps.py` - NWPS task wrappers
- `backend/tasks/pacioos.py` - PacIOOS task wrappers
- `backend/tasks/api_based.py` - Shared API-based orchestration
- `backend/tasks/surfline.py` - Surfline task wrappers
- `backend/tasks/open_meteo.py` - Open-Meteo task wrappers

**API:**

- `backend/routers/forecast.py` - API endpoints

**Testing:**

- `backend/scripts/test_file_providers.py` - Test NWPS + PacIOOS extraction
- `backend/scripts/test_api_providers.py` - Test Surfline + Open-Meteo fetching

**Dependencies:**

- Modify `backend/pyproject.toml` - Add xarray, cfgrib, netCDF4, httpx

---

## Key Design Decisions

1. **Storage: Raw provider data** - No normalization at cache layer (preserve all fields)
2. **Transformation: API layer** - Generate views on read (flexible, no data loss)
3. **Protocol-based typing** - Structural typing, no inheritance required
4. **Two provider types** - FileBasedProvider (regional files) vs APIBasedProvider (HTTP)
5. **xarray for all gridded data** - GRIB2 (cfgrib engine) and NetCDF (default engine)
6. **Batching support flag** - API providers declare batching capability
7. **Surfline: Smart batching** - Priority spots frequently, full refresh periodically
8. **Registry: Location-aware** - Auto-registers providers based on LOCATION env
9. **Tasks: Shared orchestration** - Reusable patterns for file-based and API-based providers
10. **Error handling: Per-spot isolation** - One spot failure doesn't block others
11. **PacIOOS flexibility** - GridDAP for regional (file-based), NCSS for on-demand (API-based)

---

## Performance Expectations

**File-Based Providers:**

**NWPS (GRIB2) - 2x/day:**

- Download: 62MB in 5-20 sec
- Extraction: 20 spots × 144 hours in 2-5 min (parallel)
- Storage: ~500KB Redis per model run
- Network: 124MB/day

**PacIOOS GridDAP (NetCDF) - 4x/day:**

- Download: 20-50MB in 5-15 sec (varies by region/time range)
- Extraction: 20 spots × 144 hours in 2-5 min (parallel)
- Storage: ~400KB Redis per model run
- Network: ~80-200MB/day

**API-Based Providers:**

**Surfline - Variable frequency:**

- Priority spots (20): Every 10 min = ~50KB × 144/day = 7MB/day
- All spots (150): Every 3 hours = 7.5MB × 8/day = 60MB/day
- Total: ~70MB/day

**Open-Meteo - Hourly (batched):**

- All spots (150): One request = ~200KB × 24/day = ~5MB/day
- Extremely efficient due to batching

**Total Resource Impact:**

- Network: ~300-400MB/day (negligible on home internet)
- Redis: ~10-20MB active forecast data (all providers)
- CPU: 5-10 min processing 4-6x/day (file-based) + minimal for HTTP requests
- Disk: ~100MB temporary during file-based processing (deleted after 30min)

---

## Next Steps After MVP

1. **Monitoring** - Track task failures, stale data, API latency
2. **Unit conversion** - Backend handles ft↔m, mph↔m/s conversions
3. **More providers**:
   - NOAA NDBC buoys (observations for forecast validation)
   - Windy.com API (alternative global forecasts)
   - Regional models (RTOFS for currents, NAM for wind)
4. **Forecast quality** - Compare predictions vs actual conditions (learn which provider is best per spot)
5. **User preferences** - Let users choose default provider or blend multiple
6. **Alerts** - "Notify me when Ho'okipa hits 15ft+ with offshore winds"
7. **Historical analysis** - Store forecasts in DB for accuracy tracking
8. **Provider comparison views** - Side-by-side NWPS vs Surfline vs PacIOOS vs Open-Meteo
9. **Smart caching** - Cache API layer views for frequently accessed endpoints
10. **PacIOOS NCSS fallback** - Use NCSS API for on-demand spot queries when GridDAP is stale
