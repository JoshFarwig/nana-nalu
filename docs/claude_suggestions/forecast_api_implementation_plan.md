# Forecast API Endpoint Implementation Plan

## Overview

Implement FastAPI endpoints to retrieve surf forecast data from Redis (populated by Celery workers) with unified, provider-agnostic schemas. The architecture separates concerns: service layer (Redis retrieval), schema layer (data normalization), and API layer (routing).

## User Requirements Summary

- **Endpoints**: `GET /forecasts/{spot_id}` with optional `?provider=nwps` filtering
- **Data Schema**: Unified/normalized schema mapping provider-specific fields to common names
- **Strategy**: Static endpoints returning 404 when no data exists
- **Separation**: Service returns raw dicts; Pydantic schemas handle transformation

## Architecture Decisions

1. **Service Layer Returns Raw Data** - `ForecastService` retrieves dicts from Redis without transformation
2. **Schemas Handle Normalization** - Provider-specific transformers map raw fields to unified schema
3. **Static Endpoints** - All spots get forecast endpoints; return 404 if no data exists
4. **DB Validation** - Always validate spot exists before Redis lookup for clear error messages
5. **Partial Success** - Return 200 with available providers + list of unavailable providers

---

## Implementation Steps

### Step 1: Create Unified Forecast Schema

**File**: `backend/schemas/forecast_schema.py` (NEW)

**Components**:

- `WaveDataPoint` - Single timestep with normalized fields:
  - `wave_height_m`, `swell_direction_deg`, `swell_period_s`
  - `wind_wave_height_m`, `water_temperature_c`
  - `wind_speed_ms`, `wind_direction_deg`
- `GridMetadata` - Spatial resolution info (lat/lon, distance_km)
- `ForecastMetadata` - Provider info, analysis_time, forecast_horizon_hours
  - Computed field: `hours_since_analysis` for data freshness
- `ProviderForecast` - Single provider's forecast (metadata + timeseries)
- `SpotForecast` - All providers for a spot + unavailable provider list

**NWPS Field Mapping**:

```
var_HTSGW → wave_height_m
var_DIRPW → swell_direction_deg
var_SWPER → swell_period_s
var_WIND  → wind_speed_ms
var_WDIR  → wind_direction_deg
```

**Transformer Pattern**:

- `ForecastTransformer` protocol defining `transform()` method
- `NWPSTransformer` implementing NWPS-specific mapping
- `TRANSFORMER_REGISTRY` dict for provider lookup
- Placeholders for `PacioosTransformer`, `SwanTransformer`

**Key Code Structure**:

```python
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, computed_field

class WaveDataPoint(BaseModel):
    """Single timestep of wave forecast data."""

    valid_time: datetime
    wave_height_m: Optional[float] = Field(None, description="Significant wave height (meters)")
    swell_direction_deg: Optional[float] = Field(None, ge=0, le=360)
    swell_period_s: Optional[float] = Field(None, description="Dominant wave period (seconds)")
    wind_wave_height_m: Optional[float] = None
    water_temperature_c: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    wind_direction_deg: Optional[float] = Field(None, ge=0, le=360)

class GridMetadata(BaseModel):
    """Grid cell metadata for spatial resolution info."""
    selected_lat: float
    selected_lon: float
    distance_km: float

class ForecastMetadata(BaseModel):
    """Provider-agnostic forecast metadata."""
    provider: str
    analysis_time: datetime
    forecast_horizon_hours: int
    grid_metadata: GridMetadata
    location: str

    @computed_field
    @property
    def hours_since_analysis(self) -> float:
        """Calculate freshness of forecast data."""
        delta = datetime.now(timezone.utc) - self.analysis_time
        return round(delta.total_seconds() / 3600, 1)

class ProviderForecast(BaseModel):
    """Single provider's forecast for a spot."""
    metadata: ForecastMetadata
    timeseries: List[WaveDataPoint]

class SpotForecast(BaseModel):
    """Complete forecast data for a single spot (all providers)."""
    spot_id: int
    providers: Dict[str, ProviderForecast]
    providers_unavailable: List[str] = Field(default_factory=list)

    @computed_field
    @property
    def available_providers(self) -> List[str]:
        return list(self.providers.keys())
```

**NWPSTransformer**:

```python
class NWPSTransformer:
    """Transform NWPS-specific field names to unified schema."""

    FIELD_MAPPING = {
        "var_HTSGW": "wave_height_m",
        "var_DIRPW": "swell_direction_deg",
        "var_SWPER": "swell_period_s",
        "var_WVHGT": "wind_wave_height_m",
        "var_WTMP": "water_temperature_c",
        "var_WIND": "wind_speed_ms",
        "var_WDIR": "wind_direction_deg",
    }

    @staticmethod
    def transform(raw_data: Dict[str, Any], spot_id: int) -> ProviderForecast:
        """Transform raw NWPS data from Redis to unified schema."""
        # Parse timestamps
        analysis_time = datetime.fromisoformat(raw_data["analysis_time"])
        valid_times = [datetime.fromisoformat(vt) for vt in raw_data["valid_times"]]

        # Build metadata
        metadata = ForecastMetadata(
            provider="nwps",
            analysis_time=analysis_time,
            forecast_horizon_hours=len(valid_times),
            grid_metadata=GridMetadata(**raw_data["grid_metadata"]),
            location=raw_data.get("location", "unknown")
        )

        # Transform time series data
        timeseries = []
        raw_vars = raw_data["data"]

        for i, valid_time in enumerate(valid_times):
            point_data = {"valid_time": valid_time}
            for nwps_var, unified_field in NWPSTransformer.FIELD_MAPPING.items():
                if nwps_var in raw_vars:
                    point_data[unified_field] = raw_vars[nwps_var][i]
            timeseries.append(WaveDataPoint(**point_data))

        return ProviderForecast(metadata=metadata, timeseries=timeseries)

# Registry for provider transformers
TRANSFORMER_REGISTRY: Dict[str, ForecastTransformer] = {
    "nwps": NWPSTransformer,
    "pacioos": PacioosTransformer,  # Placeholder
    "swan": SwanTransformer,         # Placeholder
}
```

---

### Step 2: Create Forecast Service

**File**: `backend/services/forecast/forecast_service.py` (NEW)

**Key Methods**:

- `_build_forecast_key(provider, location, spot_id)` → Redis key construction
- `_get_nwps_keys_for_spot(spot_id, lat, lon)` → Uses existing `get_covering_locations()` util
- `get_provider_forecast(provider, location, spot_id)` → Returns raw dict or None
  - Handles JSON parsing
  - Logs warnings for missing data
  - Injects `location` field into returned dict (needed by transformer)
- `get_all_forecasts_for_spot(spot_id, lat, lon, providers)` → Returns dict of provider → raw forecast
  - MVP: Only queries NWPS
  - Returns None for unavailable providers

**Dependencies**: Receives `AsyncRedisManager` via DI

**Key Code Structure**:

```python
import json
import logging
from typing import Dict, Optional, List
from core.redis import AsyncRedisManager
from services.forecast.providers.nwps.utils import get_covering_locations

class ForecastService:
    """Service for retrieving forecast data from Redis."""

    def __init__(self, redis_manager: AsyncRedisManager):
        self.redis = redis_manager

    @staticmethod
    def _build_forecast_key(provider: str, location: str, spot_id: int) -> str:
        """
        Build Redis key for forecast data.
        Pattern: forecast:{provider}:{location}:{spot_id}
        """
        return f"forecast:{provider}:{location}:{spot_id}"

    async def get_provider_forecast(
        self,
        provider: str,
        location: str,
        spot_id: int
    ) -> Optional[Dict]:
        """Retrieve single provider forecast from Redis."""
        key = self._build_forecast_key(provider, location, spot_id)

        try:
            data = await self.redis.client.get(key)
            if data is None:
                return None

            forecast_dict = json.loads(data)
            forecast_dict["location"] = location  # Enrich for transformer
            return forecast_dict

        except json.JSONDecodeError:
            logger.error(f"Failed to parse forecast JSON from Redis: {key}")
            return None

    async def get_all_forecasts_for_spot(
        self,
        spot_id: int,
        lat: float,
        lon: float,
        providers: Optional[List[str]] = None
    ) -> Dict[str, Optional[Dict]]:
        """Retrieve forecasts from all available providers for a spot."""
        forecasts = {}

        if providers is None:
            providers_to_query = ["nwps"]  # MVP: only NWPS
        else:
            providers_to_query = providers

        for provider in providers_to_query:
            if provider == "nwps":
                nwps_keys = self._get_nwps_keys_for_spot(spot_id, lat, lon)
                for location_name, key in nwps_keys.items():
                    forecast = await self.get_provider_forecast("nwps", location_name, spot_id)
                    if forecast:
                        forecasts["nwps"] = forecast
                        break
                if "nwps" not in forecasts:
                    forecasts["nwps"] = None
            else:
                forecasts[provider] = None

        return forecasts
```

---

### Step 3: Create Custom Exceptions

**File**: `backend/core/exceptions/forecast_exceptions.py` (NEW)

**Exceptions**:

- `ForecastNotFoundError` - Inherits from `NanaNaluException`
  - Returns 404 status code
  - Includes spot_id and provider in details
- `ForecastTransformationError` - Inherits from `NanaNaluException`
  - Returns 500 status code
  - Includes provider, spot_id, original error in details

**Pattern**: Follow existing exception pattern in `backend/core/exceptions/base.py`

**Key Code Structure**:

```python
from typing import Any, Optional
from fastapi import status
from core.exceptions.base import NanaNaluException

class ForecastNotFoundError(NanaNaluException):
    """Raised when no forecast data exists for the requested spot/provider."""

    def __init__(
        self,
        spot_id: int,
        provider: Optional[str] = None,
        details: dict[str, Any] | None = None,
    ):
        if provider:
            message = f"No forecast data available for spot {spot_id} from provider {provider}"
        else:
            message = f"No forecast data available for spot {spot_id} from any provider"

        super().__init__(
            message=message,
            error_code="forecast_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details or {"spot_id": spot_id, "provider": provider},
        )

class ForecastTransformationError(NanaNaluException):
    """Raised when forecast data transformation fails."""

    def __init__(
        self,
        provider: str,
        spot_id: int,
        original_error: str,
        details: dict[str, Any] | None = None,
    ):
        message = f"Failed to transform {provider} forecast data for spot {spot_id}"

        super().__init__(
            message=message,
            error_code="forecast_transformation_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details or {"provider": provider, "spot_id": spot_id, "error": original_error},
        )
```

---

### Step 4: Create Service Dependencies

**File**: `backend/core/dependencies/services.py` (NEW)

**Functions**:

- `get_forecast_service(redis_manager=Depends(get_redis_manager))` → ForecastService
- `get_surf_spot_repository(session=Depends(get_db_session))` → AsyncSurfSpotRepository

**Pattern**: Follow existing DI pattern in `backend/core/dependencies/core.py`

**Key Code Structure**:

```python
import logging
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.redis import AsyncRedisManager
from core.dependencies.core import get_redis_manager, get_db_session
from services.forecast.forecast_service import ForecastService
from repositories.surf_spot_repository import AsyncSurfSpotRepository

logger = logging.getLogger(__name__)

def get_forecast_service(
    redis_manager: AsyncRedisManager = Depends(get_redis_manager),
) -> ForecastService:
    """Get ForecastService instance with Redis dependency."""
    return ForecastService(redis_manager)

def get_surf_spot_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncSurfSpotRepository:
    """Get AsyncSurfSpotRepository instance with DB session dependency."""
    return AsyncSurfSpotRepository(session)
```

---

### Step 5: Create API Routes

**File**: `backend/api/v1/routes/forecasts.py` (NEW)

**Endpoints**:

1. **`GET /forecasts/{spot_id}`**
   - Path param: `spot_id` (int, ge=1)
   - Query param: `provider` (optional str)
   - Response model: `SuccessResponse[SpotForecast]`
   - Logic:
     1. Get spot coordinates from DB (raises 404 if not found)
     2. Determine provider filter (single or all)
     3. Fetch raw forecasts from service
     4. Transform using registered transformers
     5. Return 404 if no transformed forecasts available
     6. Return 200 with available + unavailable providers

2. **`GET /forecasts/{spot_id}/providers`**
   - Check which providers have data available
   - Returns: `{available_providers: [], unavailable_providers: []}`

**Helper Functions**:

- `_get_spot_coordinates(spot_id, spot_repo)` → Raises HTTPException 404 if spot doesn't exist
- `_transform_forecasts(raw_forecasts, spot_id)` → Returns (transformed_dict, unavailable_list)
  - Catches transformer errors gracefully
  - Logs warnings for transformation failures

**Error Handling**:

- 404: Spot doesn't exist OR no forecast data available
- 500: Transformation errors, Redis failures

**Key Code Structure**:

```python
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status

from core.dependencies.services import get_forecast_service, get_surf_spot_repository
from services.forecast.forecast_service import ForecastService
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from schemas.forecast_schema import SpotForecast, ProviderForecast, get_transformer
from schemas.response_schema import SuccessResponse
from core.exceptions.forecast_exceptions import ForecastNotFoundError

logger = logging.getLogger(__name__)
router = APIRouter()

async def _get_spot_coordinates(
    spot_id: int,
    spot_repo: AsyncSurfSpotRepository
) -> tuple[float, float]:
    """Get spot coordinates from database. Raises 404 if spot doesn't exist."""
    coords = await spot_repo.get_coordinates(spot_id)
    if not coords:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Surf spot {spot_id} does not exist"
        )
    return coords["latitude"], coords["longitude"]

def _transform_forecasts(
    raw_forecasts: dict[str, Optional[dict]],
    spot_id: int
) -> tuple[dict[str, ProviderForecast], list[str]]:
    """Transform raw forecast dicts to unified schema."""
    transformed = {}
    unavailable = []

    for provider, raw_data in raw_forecasts.items():
        if raw_data is None:
            unavailable.append(provider)
            continue

        try:
            transformer = get_transformer(provider)
            transformed[provider] = transformer.transform(raw_data, spot_id)
        except Exception as e:
            logger.warning(f"Failed to transform {provider} forecast: {e}")
            unavailable.append(provider)

    return transformed, unavailable

@router.get(
    "/{spot_id}",
    response_model=SuccessResponse[SpotForecast],
    summary="Get forecast for a surf spot",
)
async def get_spot_forecast(
    spot_id: int = Path(..., ge=1),
    provider: Optional[str] = Query(None),
    forecast_service: ForecastService = Depends(get_forecast_service),
    spot_repo: AsyncSurfSpotRepository = Depends(get_surf_spot_repository),
):
    """Get forecast data for a surf spot, optionally filtered by provider."""
    # Get spot coordinates
    lat, lon = await _get_spot_coordinates(spot_id, spot_repo)

    # Determine provider filter
    provider_filter = [provider] if provider else None

    # Fetch raw forecasts
    raw_forecasts = await forecast_service.get_all_forecasts_for_spot(
        spot_id, lat, lon, providers=provider_filter
    )

    # Transform to unified schema
    transformed_forecasts, unavailable = _transform_forecasts(raw_forecasts, spot_id)

    # Check if we got any data
    if not transformed_forecasts:
        raise ForecastNotFoundError(spot_id=spot_id, provider=provider)

    # Build response
    spot_forecast = SpotForecast(
        spot_id=spot_id,
        providers=transformed_forecasts,
        providers_unavailable=unavailable
    )

    return SuccessResponse(
        success=True,
        message="Forecast retrieved successfully",
        data=spot_forecast
    )

@router.get("/{spot_id}/providers")
async def get_available_providers(
    spot_id: int = Path(..., ge=1),
    forecast_service: ForecastService = Depends(get_forecast_service),
    spot_repo: AsyncSurfSpotRepository = Depends(get_surf_spot_repository),
):
    """Check which forecast providers have data for this spot."""
    lat, lon = await _get_spot_coordinates(spot_id, spot_repo)
    raw_forecasts = await forecast_service.get_all_forecasts_for_spot(spot_id, lat, lon)

    available = [p for p, data in raw_forecasts.items() if data is not None]
    unavailable = [p for p, data in raw_forecasts.items() if data is None]

    return SuccessResponse(
        success=True,
        message="Provider availability checked",
        data={
            "spot_id": spot_id,
            "available_providers": available,
            "unavailable_providers": unavailable,
        }
    )
```

---

### Step 6: Register Router

**File**: `backend/api/v1/app.py` (MODIFY lines 130-134)

**Change**:

```python
# Add import at top
from api.v1.routes import forecasts

# Replace TODO comment (lines 130-134) with:
app.include_router(
    forecasts.router,
    prefix="/api/v1/forecasts",
    tags=["forecasts"]
)
```

---

### Step 7: Update Celery Task

**File**: `backend/workers/tasks/nwps.py` (MODIFY line 219)

**Change**: Inject `location` field into forecast data before storing in Redis

```python
# Around line 217-220, in the Redis storage loop:
with redis_manager.client.pipeline() as pipe:
    for spot_id, spot_data in forecasts.items():
        spot_data["location"] = loc  # ADD THIS LINE
        key = f"forecast:nwps:{loc}:{spot_id}"
        pipe.setex(key, timedelta(hours=14), json.dumps(spot_data))
```

**Reason**: Transformer needs location field; currently missing from stored data

---

## Critical Files

**New Files** (5 total):

1. `backend/schemas/forecast_schema.py` - Unified schema + transformers (~400 lines)
2. `backend/services/forecast/forecast_service.py` - Redis retrieval (~200 lines)
3. `backend/core/dependencies/services.py` - DI setup (~30 lines)
4. `backend/api/v1/routes/forecasts.py` - API endpoints (~250 lines)
5. `backend/core/exceptions/forecast_exceptions.py` - Custom exceptions (~40 lines)

**Modified Files** (2 total):

1. `backend/api/v1/app.py` - Register router (4 lines changed)
2. `backend/workers/tasks/nwps.py` - Add location to Redis data (1 line added)

**Reference Files** (existing patterns to follow):

- `backend/core/dependencies/core.py` - DI pattern
- `backend/schemas/response_schema.py` - Response envelope pattern
- `backend/core/exceptions/base.py` - Exception pattern
- `backend/api/v1/routes/users.py` - Route pattern

---

## Example API Response

**Request**: `GET /api/v1/forecasts/42`

**Response**:

```json
{
  "success": true,
  "message": "Forecast retrieved successfully",
  "data": {
    "spot_id": 42,
    "providers": {
      "nwps": {
        "metadata": {
          "provider": "nwps",
          "analysis_time": "2025-01-26T06:00:00+00:00",
          "forecast_horizon_hours": 144,
          "hours_since_analysis": 2.5,
          "grid_metadata": {
            "selected_lat": 20.891,
            "selected_lon": 156.340,
            "distance_km": 0.45
          },
          "location": "maui"
        },
        "timeseries": [
          {
            "valid_time": "2025-01-26T06:00:00+00:00",
            "wave_height_m": 4.2,
            "swell_direction_deg": 270.0,
            "swell_period_s": 12.5,
            "wind_wave_height_m": null,
            "water_temperature_c": null,
            "wind_speed_ms": null,
            "wind_direction_deg": null
          },
          {
            "valid_time": "2025-01-26T07:00:00+00:00",
            "wave_height_m": 4.5,
            "swell_direction_deg": 272.0,
            "swell_period_s": 12.3,
            "wind_wave_height_m": null,
            "water_temperature_c": null,
            "wind_speed_ms": null,
            "wind_direction_deg": null
          }
        ]
      }
    },
    "providers_unavailable": [],
    "available_providers": ["nwps"]
  }
}
```

**Request**: `GET /api/v1/forecasts/42?provider=nwps`

**Response**: Same as above (filtered to NWPS only)

**Request**: `GET /api/v1/forecasts/42/providers`

**Response**:

```json
{
  "success": true,
  "message": "Provider availability checked",
  "data": {
    "spot_id": 42,
    "available_providers": ["nwps"],
    "unavailable_providers": ["pacioos", "swan"]
  }
}
```

**Request**: `GET /api/v1/forecasts/999` (spot doesn't exist)

**Response**: 404

```json
{
  "success": false,
  "message": "Surf spot 999 does not exist",
  "error_code": "not_found",
  "details": null
}
```

---

## Testing Strategy

### Unit Tests

**`tests/unit/schemas/test_forecast_schema.py`**:

- Field validation (ranges, types, optional fields)
- Computed field calculations (`hours_since_analysis`)
- Transformer logic with mock NWPS data
- Registry lookup functionality

**`tests/unit/services/test_forecast_service.py`**:

- Redis key construction for different providers/locations
- Mock Redis client responses
- Multi-provider aggregation logic
- JSON parsing error handling

**`tests/unit/api/test_forecasts.py`**:

- Mocked service responses
- 404 handling for missing spots
- 404 handling for missing forecast data
- Query parameter validation
- Provider filtering logic

### Integration Tests

**`tests/integration/test_forecast_api.py`**:

- Full end-to-end API request/response cycle
- Real Redis interactions (test database)
- Provider filtering with actual data
- Coordinate lookup from database
- Error scenarios (spot not found, no data)

**`tests/integration/test_transformers.py`**:

- Transform real NWPS data from Redis
- Validate schema compliance
- Test with actual forecast data structure

### Manual Testing

```bash
# Start services
docker-compose up -d

# Get all providers for a spot
curl -X GET "http://localhost:8000/api/v1/forecasts/1" | jq

# Filter by specific provider
curl -X GET "http://localhost:8000/api/v1/forecasts/1?provider=nwps" | jq

# Check provider availability
curl -X GET "http://localhost:8000/api/v1/forecasts/1/providers" | jq

# Test 404 - spot doesn't exist
curl -X GET "http://localhost:8000/api/v1/forecasts/99999" | jq

# View auto-generated API docs
open http://localhost:8000/docs
```

---

## Deployment Checklist

1. ✅ Create all 5 new files with complete implementations
2. ✅ Modify `app.py` to register forecasts router
3. ✅ Update Celery task to include `location` field in Redis data
4. ✅ Run existing tests to ensure no regressions
5. ✅ Write unit tests for new schemas, service, and routes
6. ✅ Test with real NWPS data in development environment
7. ✅ Deploy backend with new routes
8. ✅ Monitor logs for transformation errors
9. ✅ Verify Swagger docs at `/docs` endpoint
10. ✅ Test from frontend or API client

---

## Future Extensions

1. **Bulk Endpoint**: `GET /forecasts?spot_ids=1,2,3` for multi-spot queries
2. **Time Filtering**: `?start_time=...&end_time=...` for time-range slicing
3. **Field Selection**: `?fields=wave_height_m,swell_direction_deg` for bandwidth optimization
4. **Response Caching**: Add Redis caching layer for transformed responses (short TTL)
5. **Dynamic Endpoint Registration**: Register endpoints based on provider grid coverage
6. **WebSocket Support**: Real-time updates when new forecast runs available
7. **Forecast Comparison**: Side-by-side comparison of different providers
8. **Historical Data**: Archive and retrieve past forecasts for accuracy analysis
9. **Provider Weights**: Allow users to set provider preferences
10. **Custom Alerts**: Notify when conditions match user-defined criteria

---

## Architecture Notes

### Design Patterns Used

1. **Dependency Injection** - FastAPI's `Depends()` for loose coupling
2. **Repository Pattern** - Data access abstraction (spot coordinates)
3. **Service Layer** - Business logic separation (forecast retrieval)
4. **Transformer Pattern** - Provider-specific normalization via registry
5. **Protocol-Based Design** - Extensible transformer interface

### Key Trade-offs

| Decision | Rationale |
|----------|-----------|
| Transform in API layer | Service stays generic/reusable; API handles presentation |
| DB validation for spots | Clear 404 errors; minimal latency overhead |
| Partial success (200 OK) | Prefer availability; frontend can gracefully degrade |
| Static endpoints | Simpler MVP; dynamic registration can be added later |
| Computed freshness field | Always accurate; no additional storage needed |

### Error Handling Strategy

- **404 Not Found**: Spot doesn't exist OR no forecast data available
- **500 Internal Server Error**: Transformation failures, Redis errors
- **422 Unprocessable Entity**: Invalid query parameters (FastAPI automatic)

All exceptions logged with structured context for debugging.

---

## Monitoring & Observability

### Key Metrics to Track

1. **Request Metrics**:
   - Requests per minute by endpoint
   - Response times (p50, p95, p99)
   - Error rates by status code

2. **Forecast Data Metrics**:
   - Cache hit rates per provider
   - Transformation failure rates
   - Average forecast age (`hours_since_analysis`)

3. **Provider Health**:
   - Availability percentage per provider
   - Data freshness trends
   - Missing forecast alerts

### Structured Logging

All logs include context for debugging:

```python
logger.info(
    "Forecast retrieved",
    extra={
        "spot_id": 42,
        "providers": ["nwps"],
        "response_time_ms": 45.2,
        "forecast_age_hours": 2.5
    }
)
```

---

## Summary

This implementation provides a clean, extensible API for surf forecast data with:

- ✅ Unified schemas across providers
- ✅ Separation of concerns (service/schema/API layers)
- ✅ Flexible querying (all providers or filtered)
- ✅ Graceful error handling with clear messages
- ✅ Ready for future provider additions (PacIOOS, SWAN)
- ✅ Production-ready logging and monitoring hooks

The architecture follows existing patterns in the codebase while introducing a scalable foundation for multi-provider forecast data delivery.
