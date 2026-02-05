# Wave Forecast Schema — Refactoring Implementation Plan

## Overview

Refactor `WaveData` in `forecast_schema.py` to support swell partitioning and fix direction conventions.
The current schema treats swell as a single value, but planned model additions (GFS Wave, Hawaii WW3) provide
2-3 distinct swell systems plus wind waves, each with their own height, period, and direction.

**Scope:** Schema changes + NWPS mapper update. No new model pipelines — only future-proofing the schema
so GFS Wave and Hawaii WW3 can be added without another schema refactor.

**Prerequisite for:** `spot_condition_profile_implementation_plan.md` — that feature's `WaveConditions`
schema must be built against the NEW field names from this refactor.

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Structure | Nested `SwellPartition` objects | Type-safe, self-documenting, matches GFS Wave data structure |
| NWPS swell mapping | `shts` → `primary_swell.height` | NWPS provides one swell — treat as primary, secondary/tertiary stay `None` |
| Direction convention | Standardize all wave directions to `degrees_true_toward` | Matches oceanographic convention; convert NWPS "from" → "toward" at ingestion |
| `mean_direction` / `mean_period` | Remove | Never populated by any provider — peak vs mean is a calculation method, not two values |
| `height` field | Rename to `significant_height` | Removes ambiguity about what "height" means |
| Future models | Add `GFS_WAVE` and `WAVEWATCH3` to `ForecastModel` enum now | Avoids future schema migration for enum additions |
| Condition profiles | Per-partition conditions supported | `WaveConditions` will have `primary_swell`, `secondary_swell` condition fields |
| Breaking change | Yes — no phased migration | Pre-launch app, no external clients. Clean break is simpler. |

---

## Files to Modify (4)

| # | File | Changes |
|---|------|---------|
| 1 | `backend/services/forecast/forecast_schema.py` | Add `SwellPartition`, refactor `WaveData`, update `WaveUnits`, add enum values to `ForecastModel`, update `ProviderForecastResponse._compute_units()` |
| 2 | `backend/workflows/nomads/mapper.py` | Update `map_nwps_forecast()` — new field names, map swell dir/period, direction conversion |
| 3 | `backend/workflows/pacioos/mapper.py` | Update docstrings on TODO stubs to reference new field names |
| 4 | `backend/services/forecast/nomads_config.py` | Add `GFS_WAVE` to `NOMADSModel` enum |

All paths relative to project root.

---

## Step 1 — Schema Changes (`forecast_schema.py`)

### 1a. Add `SwellPartition` model (NEW — place above `WaveData`)

```python
class SwellPartition(BaseModel):
    """
    Individual swell component with direction, period, and height.

    Represents a single swell system (e.g., west swell, south swell).
    """

    model_config = ConfigDict(extra="forbid")

    height: float | None = Field(
        default=None,
        description="Swell height (m)"
    )
    period: float | None = Field(
        default=None,
        description="Swell period (s)"
    )
    direction: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Swell direction, degrees true (toward)",
    )
```

### 1b. Refactor `WaveData` (REPLACE existing class entirely)

**Remove:** `height`, `swell_height`, `mean_direction`, `mean_period`
**Rename:** `height` → `significant_height`
**Keep:** `peak_period`, `peak_direction` (fix direction description to "toward")
**Add:** `wind_wave_height`, `wind_wave_period`, `wind_wave_direction`, `primary_swell`, `secondary_swell`, `tertiary_swell`

```python
class WaveData(BaseModel):
    """
    Unified wave measurements representing complete sea state.

    Includes total combined conditions, wind-generated waves,
    and individual swell partitions ordered by energy/significance.

    All heights in meters, directions in degrees true (0-360, toward),
    periods in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    # ===== Total Sea State (All Components Combined) =====
    significant_height: float | None = Field(
        default=None,
        description="Significant wave height - combined wind waves and all swells (m)"
    )
    peak_period: float | None = Field(
        default=None,
        description="Peak period of dominant wave component (s)"
    )
    peak_direction: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Direction of dominant wave component, degrees true (toward)",
    )

    # ===== Wind Waves (Locally Generated) =====
    wind_wave_height: float | None = Field(
        default=None,
        description="Significant height of wind waves (m)"
    )
    wind_wave_period: float | None = Field(
        default=None,
        description="Period of wind waves (s)"
    )
    wind_wave_direction: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Direction of wind waves, degrees true (toward)",
    )

    # ===== Swell Partitions (Remotely Generated) =====
    # Ordered by significance: primary > secondary > tertiary
    primary_swell: SwellPartition | None = Field(
        default=None,
        description="Dominant swell system"
    )
    secondary_swell: SwellPartition | None = Field(
        default=None,
        description="Second most significant swell system"
    )
    tertiary_swell: SwellPartition | None = Field(
        default=None,
        description="Third swell system (rare, only from some models)"
    )
```

### 1c. Refactor `WaveUnits` (REPLACE existing class entirely)

```python
class WaveUnits(BaseModel):
    """Documents units for wave measurements."""

    model_config = ConfigDict(frozen=True)

    # Total sea state
    significant_height: Literal["m"] = "m"
    peak_period: Literal["s"] = "s"
    peak_direction: Literal["degrees_true_toward"] = "degrees_true_toward"

    # Wind waves
    wind_wave_height: Literal["m"] = "m"
    wind_wave_period: Literal["s"] = "s"
    wind_wave_direction: Literal["degrees_true_toward"] = "degrees_true_toward"

    # Swell components (applies to all partitions)
    swell_height: Literal["m"] = "m"
    swell_period: Literal["s"] = "s"
    swell_direction: Literal["degrees_true_toward"] = "degrees_true_toward"
```

### 1d. Add enum values to `ForecastModel`

Add below existing entries:

```python
class ForecastModel(str, Enum):
    """Specific forecast model/system (generic, not region-specific)."""

    # NOMADS models
    NWPS = "nwps"
    GFS_WAVE = "gfs_wave"

    # PacIOOS models
    TIDE = "tide"
    SWAN = "swan"
    WRF = "wrf"
    WAVEWATCH3 = "wavewatch3"
```

### 1e. Update `ProviderForecastResponse._compute_units()`

The `_compute_units()` method (lines 269-319) collects field names from `model_dump(exclude_none=True)`
and matches them against unit model fields. With nested `SwellPartition`, the dumped wave data will
contain keys like `primary_swell`, `secondary_swell`, `tertiary_swell` (as dicts), not flat field names.

**Required change:** When building `wave_fields`, flatten nested swell partition keys into the
corresponding unit field names. If `primary_swell`, `secondary_swell`, or `tertiary_swell` exists
in the dumped data, add `swell_height`, `swell_period`, `swell_direction` to `wave_fields` so
the units map includes swell units.

```python
# Inside _compute_units(), after collecting wave_fields:
if point.wave:
    wave_data = point.wave.model_dump(exclude_none=True)
    # Flatten swell partition keys to unit field names
    for swell_key in ("primary_swell", "secondary_swell", "tertiary_swell"):
        if swell_key in wave_data:
            swell_data = wave_data.pop(swell_key)
            if "height" in swell_data:
                wave_data["swell_height"] = True
            if "period" in swell_data:
                wave_data["swell_period"] = True
            if "direction" in swell_data:
                wave_data["swell_direction"] = True
    wave_fields.update(wave_data.keys())
```

---

## Step 2 — NWPS Mapper Update (`nomads/mapper.py`)

### Actual GRIB2 variables (from data inspection)

The NWPS GRIB2 file contains these variables after cfgrib extraction:

| cfgrib shortName | Description | Unit | Current Mapping | New Mapping |
|-----------------|-------------|------|-----------------|-------------|
| `swh` | Significant height of combined wind waves and swell | m | `wave.height` | `wave.significant_height` |
| `dirpw` | Primary wave direction | degrees true | `wave.peak_direction` | `wave.peak_direction` + convert to "toward" |
| `perpw` | Primary wave mean period | s | `wave.peak_period` | `wave.peak_period` (no change) |
| `shts` | Significant height of total swell | m | `wave.swell_height` | `wave.primary_swell.height` |
| `ws` | Wind speed | m/s | `wind.speed` | No change |
| `wdir` | Wind direction | degrees true | `wind.direction` | No change (wind stays "from") |
| `zos` | Sea surface height | m | `tide.height` | No change |
| `dirc` | Current direction | degrees true | **NOT MAPPED** | `current.direction` (optional, separate scope) |
| `spc` | Current speed | m/s | **NOT MAPPED** | `current.speed` (optional, separate scope) |

**NWPS swell limitation:** NWPS provides only swell HEIGHT (`shts`), not swell direction or period
as separate variables. The config requests `var_SWDIR` and `var_SWPER` from the grib_filter, but these
are NOMADS API aliases that resolve to `dirpw` and `perpw` (the combined primary wave values) — they do
NOT produce distinct swell-specific variables in the GRIB2 output.

**Consequence for primary_swell:** Only `height` can be populated. `period` and `direction` remain `None`.
This is physically reasonable — when NWPS reports a single swell height, the primary wave direction and
period (`dirpw`, `perpw`) are heavily influenced by swell anyway, so users can reference the top-level
`peak_direction` and `peak_period` fields.

**Current data (`dirc`, `spc`):** Available in the GRIB2 but unmapped. These can be mapped to
`CurrentData` in a future pass — out of scope for this wave schema refactor.

**Config cleanup:** Consider removing `var_SWDIR` and `var_SWPER` from `MauiNWPSConfig.params`
since they don't produce separate variables. Not blocking — they're harmless but misleading.

### Updated mapper function

Import `SwellPartition` alongside existing imports.

```python
from services.forecast.forecast_schema import (
    GridMetadata,
    SwellPartition,
    TideData,
    WaveData,
    WindData,
    ForecastPoint,
    ForecastProvider,
    ForecastModel,
    ProviderForecast,
)


def _wave_direction_to_toward(direction_from: float | None) -> float | None:
    """Convert wave direction from 'from' convention to 'toward' convention."""
    if direction_from is None:
        return None
    return (direction_from + 180) % 360


def map_nwps_forecast(
    spot_id: int, location: str, nwps_forecast_data: dict, data_summary: dict[str, str]
) -> ProviderForecast:
    """
    Map NWPS data fields to unified schema.

    NWPS provides only swell height (shts) — no separate swell direction or period.
    Maps shts to primary_swell.height; period and direction remain None.

    Direction convention: NWPS reports wave direction as "from" (Degree true).
    Converted to "toward" at ingestion: (direction + 180) % 360.
    Wind direction remains "from" (meteorological convention).
    """
    forecast = []

    for i, valid_time in enumerate(nwps_forecast_data["valid_times"]):
        data = nwps_forecast_data["data"]

        wave = WaveData(
            significant_height=data["swh"][i],
            peak_period=data["perpw"][i],
            peak_direction=_wave_direction_to_toward(data["dirpw"][i]),
            primary_swell=SwellPartition(
                height=data["shts"][i],
            ),
        )

        wind = WindData(
            speed=data["ws"][i],
            direction=data["wdir"][i],
        )

        tide = TideData(height=data["zos"][i])

        forecast.append(
            ForecastPoint(valid_time=valid_time, wave=wave, wind=wind, tide=tide)
        )

    return ProviderForecast(
        spot_id=spot_id,
        provider=ForecastProvider.NOMADS,
        model=ForecastModel.NWPS,
        location=location,
        analysis_time=nwps_forecast_data["analysis_time"],
        grid_metadata=GridMetadata(
            selected_lat=nwps_forecast_data["grid_metadata"]["selected_lat"],
            selected_lon=nwps_forecast_data["grid_metadata"]["selected_lon"],
            distance_km=nwps_forecast_data["grid_metadata"]["distance_km"],
        ),
        data_summary=data_summary,
        forecast=forecast,
    )
```

---

## Step 3 — PacIOOS Mapper Docstring Updates (`pacioos/mapper.py`)

Update the TODO stub docstrings to reference new field names:

```python
def map_pacioos_swan_forecast(...):
    """
    Map PacIOOS SWAN wave model forecast to unified schema.

    Maps to: wave.significant_height, wave.peak_direction, wave.peak_period
    """
    # TODO:
    pass
```

No functional changes — SWAN/WRF are not implemented yet.

---

## Step 4 — NOMADS Config Enum (`nomads_config.py`)

Add `GFS_WAVE` to the `NOMADSModel` enum for future use:

```python
class NOMADSModel(str, Enum):
    """Available NOMADS ocean models."""

    NWPS = "nwps"
    GFS_WAVE = "gfs_wave"
```

---

## Existing Redis Data

After this refactor, any forecast data currently stored in Redis will fail deserialization because
field names changed (`height` → `significant_height`, `swell_height` removed, etc.).

**Resolution:** Redis keys have TTLs (NWPS: 14 hours, Tide: 7 days). Either:
- Wait for natural expiry (forecasts auto-refresh)
- Flush forecast keys manually: `redis-cli KEYS "forecast:*" | xargs redis-cli DEL`

Tide data (`TideData`) is unchanged, so `forecast:pacioos:tide:*` keys remain valid.

---

## Impact on Condition Profile Feature

The `spot_condition_profile_implementation_plan.md` references `WaveConditions` with fields
that match the OLD `WaveData` schema. After this refactor, update the condition profile plan:

### Old `WaveConditions` (from condition profile plan)

```python
class WaveConditions(BaseModel):
    height: RangeCondition | None = None
    swell_height: RangeCondition | None = None
    peak_period: RangeCondition | None = None
    peak_direction: RangeCondition | None = None
```

### New `WaveConditions` (aligned with refactored schema)

```python
class SwellConditions(BaseModel):
    """Condition ranges for a swell partition."""
    height: RangeCondition | None = None
    period: RangeCondition | None = None
    direction: RangeCondition | None = None  # wraps around north


class WaveConditions(BaseModel):
    """Condition ranges for wave data. Maps to ForecastPoint.wave (WaveData)."""
    significant_height: RangeCondition | None = None   # → wave.significant_height (m)
    peak_period: RangeCondition | None = None           # → wave.peak_period (s)
    peak_direction: RangeCondition | None = None        # → wave.peak_direction (degrees, wraps)
    wind_wave_height: RangeCondition | None = None      # → wave.wind_wave_height (m)
    wind_wave_period: RangeCondition | None = None      # → wave.wind_wave_period (s)
    wind_wave_direction: RangeCondition | None = None   # → wave.wind_wave_direction (degrees, wraps)
    primary_swell: SwellConditions | None = None        # → wave.primary_swell.*
    secondary_swell: SwellConditions | None = None      # → wave.secondary_swell.*
```

### Updated Field-to-ForecastPoint Mapping

| Condition Field | ForecastPoint Path | Unit |
|---|---|---|
| `wave.significant_height` | `point.wave.significant_height` | meters |
| `wave.peak_period` | `point.wave.peak_period` | seconds |
| `wave.peak_direction` | `point.wave.peak_direction` | degrees (toward, wraps) |
| `wave.wind_wave_height` | `point.wave.wind_wave_height` | meters |
| `wave.wind_wave_period` | `point.wave.wind_wave_period` | seconds |
| `wave.wind_wave_direction` | `point.wave.wind_wave_direction` | degrees (toward, wraps) |
| `wave.primary_swell.height` | `point.wave.primary_swell.height` | meters |
| `wave.primary_swell.period` | `point.wave.primary_swell.period` | seconds |
| `wave.primary_swell.direction` | `point.wave.primary_swell.direction` | degrees (toward, wraps) |
| `wave.secondary_swell.height` | `point.wave.secondary_swell.height` | meters |
| `wave.secondary_swell.period` | `point.wave.secondary_swell.period` | seconds |
| `wave.secondary_swell.direction` | `point.wave.secondary_swell.direction` | degrees (toward, wraps) |
| `wind.speed` | `point.wind.speed` | m/s |
| `wind.direction` | `point.wind.direction` | degrees (from, wraps) |
| `tide.height` | `point.tide.height` | meters |

### Updated `_entry_matches()` logic for swell partitions

The matching engine in `spot_condition_service.py` needs to handle nested swell:

```python
# Wave checks (inside _entry_matches)
if entry.wave:
    if not point.wave:
        return False

    if entry.wave.significant_height and not self._in_range(
        point.wave.significant_height, entry.wave.significant_height
    ):
        return False
    if entry.wave.peak_period and not self._in_range(
        point.wave.peak_period, entry.wave.peak_period
    ):
        return False
    if entry.wave.peak_direction and not self._direction_in_range(
        point.wave.peak_direction, entry.wave.peak_direction
    ):
        return False

    # Wind wave checks
    if entry.wave.wind_wave_height and not self._in_range(
        point.wave.wind_wave_height, entry.wave.wind_wave_height
    ):
        return False
    if entry.wave.wind_wave_period and not self._in_range(
        point.wave.wind_wave_period, entry.wave.wind_wave_period
    ):
        return False
    if entry.wave.wind_wave_direction and not self._direction_in_range(
        point.wave.wind_wave_direction, entry.wave.wind_wave_direction
    ):
        return False

    # Primary swell checks
    if entry.wave.primary_swell:
        if not point.wave.primary_swell:
            return False
        if not self._swell_matches(point.wave.primary_swell, entry.wave.primary_swell):
            return False

    # Secondary swell checks
    if entry.wave.secondary_swell:
        if not point.wave.secondary_swell:
            return False
        if not self._swell_matches(point.wave.secondary_swell, entry.wave.secondary_swell):
            return False
```

With a helper:

```python
def _swell_matches(
    self, swell: SwellPartition, conditions: SwellConditions
) -> bool:
    """Check if a swell partition matches conditions."""
    if conditions.height and not self._in_range(swell.height, conditions.height):
        return False
    if conditions.period and not self._in_range(swell.period, conditions.period):
        return False
    if conditions.direction and not self._direction_in_range(swell.direction, conditions.direction):
        return False
    return True
```

### Updated Condition Profile Example JSONB

**"Pipeline Winter" — NWPS primary swell + PacIOOS tide:**

```json
[
  {
    "provider": "nomads:nwps",
    "wave": {
      "significant_height": { "min": 2.5, "max": 5.0 },
      "primary_swell": {
        "direction": { "min": 300, "max": 30 }
      }
    },
    "wind": {
      "speed": { "min": 0, "max": 5.0 }
    }
  },
  {
    "provider": "pacioos:tide",
    "tide": {
      "height": { "min": -0.3, "max": 0.5 }
    }
  }
]
```

---

## Future Model Reference

### GFS Wave (NOMADS, 0.16° global grid)

**When ready to implement**, create `backend/workflows/nomads/gfs_wave/` pipeline following NWPS patterns.

**GRIB2 → Schema Mapping:**

| GRIB2 Param | cfgrib shortName | Schema Field |
|-------------|-----------------|-------------|
| `HTSGW` | `swh` | `wave.significant_height` |
| `PERPW` | `perpw` | `wave.peak_period` |
| `DIRPW` | `dirpw` | `wave.peak_direction` (convert to toward) |
| `WVHGT` | `wvhgt` | `wave.wind_wave_height` |
| `WVPER` | `wvper` | `wave.wind_wave_period` |
| `WVDIR` | `wvdir` | `wave.wind_wave_direction` (convert to toward) |
| `SWELL:1` | `shts` | `wave.primary_swell.height` |
| `SWPER:1` | `swper` | `wave.primary_swell.period` |
| `SWDIR:1` | `swdir` | `wave.primary_swell.direction` (convert to toward) |
| `SWELL:2` | TBD | `wave.secondary_swell.height` |
| `SWPER:2` | TBD | `wave.secondary_swell.period` |
| `SWDIR:2` | TBD | `wave.secondary_swell.direction` (convert to toward) |
| `SWELL:3` | TBD | `wave.tertiary_swell.height` (rare) |
| `SWPER:3` | TBD | `wave.tertiary_swell.period` |
| `SWDIR:3` | TBD | `wave.tertiary_swell.direction` (convert to toward) |

**Key differences from NWPS pipeline:**
- Global grid → need subregion extraction for Hawaii bounding box
- Uses NOMADS grib_filter like NWPS (same base infrastructure)
- Provides wind waves + up to 3 swell partitions (NWPS only has 1)
- 4x daily model runs (00Z, 06Z, 12Z, 18Z) vs NWPS's 2x
- 384-hour forecast (16 days) vs NWPS's ~72 hours
- `NOMADSModel.GFS_WAVE` already added to enum
- Will need a new `GFSWaveConfig` in `nomads_config.py`
- Mapper will be similar to NWPS but populates wind waves + multiple swell partitions

### Hawaii WW3 (PacIOOS, 0.05° regional grid)

**When ready to implement**, create `backend/workflows/pacioos/ww3_hi/` pipeline following tide_mhi patterns.

**NetCDF → Schema Mapping:**

| NetCDF Variable | Schema Field |
|----------------|-------------|
| `Thgt` | `wave.significant_height` |
| `Tper` | `wave.peak_period` |
| `Tdir` | `wave.peak_direction` (check convention) |
| `whgt` | `wave.wind_wave_height` |
| `wper` | `wave.wind_wave_period` |
| `wdir` | `wave.wind_wave_direction` (check convention) |
| `shgt` | `wave.primary_swell.height` |
| `sper` | `wave.primary_swell.period` |
| `sdir` | `wave.primary_swell.direction` (check convention) |

**Key differences from tide_mhi pipeline:**
- Wave data (not tide) — populates `WaveData` instead of `TideData`
- Higher resolution (0.05°, ~5km) than GFS Wave for Hawaii
- Single swell partition (like NWPS), no secondary/tertiary
- Uses PacIOOS ERDDAP GridDAP (same infrastructure as tide_mhi)
- Will need a new `WW3Config(PacIOOSModelConfig)` in `pacioos_config.py`
- `ForecastModel.WAVEWATCH3` already added to enum
- Need to verify direction convention before implementing mapper

---

## Verification

After implementing, verify:

1. **Schema validity:** `WaveData` accepts nested `SwellPartition` objects:
   ```python
   wave = WaveData(
       significant_height=2.5,
       peak_period=14.2,
       peak_direction=285,
       primary_swell=SwellPartition(height=2.1, period=14.2, direction=285),
   )
   assert wave.secondary_swell is None  # Valid — optional
   ```

2. **Serialization roundtrip:** `ProviderForecast.to_redis_json()` / `from_redis_json()` handles nested swell

3. **Direction conversion:** NWPS mapper converts wave directions:
   ```python
   # GRIB2 says "from 90°" (waves coming from east)
   # Schema should store "toward 270°" (waves traveling west)
   assert _wave_direction_to_toward(90) == 270
   assert _wave_direction_to_toward(0) == 180
   assert _wave_direction_to_toward(180) == 0
   ```

4. **Units computation:** `ProviderForecastResponse._compute_units()` includes swell units when swell data present

5. **Wind direction unchanged:** Wind direction stays `degrees_true_from` — no conversion applied

6. **NWPS swell height only:** Mapper maps `shts` to `primary_swell.height`; `primary_swell.period` and `primary_swell.direction` are `None` (NWPS doesn't provide them separately)

7. **None handling:** Models with no wind waves (NWPS) or no secondary swell produce clean JSON with those fields excluded (`exclude_none=True`)

---

## Implementation Order

1. `forecast_schema.py` — Add `SwellPartition`, refactor `WaveData`, update `WaveUnits`, add `ForecastModel` enum values, update `_compute_units()`
2. `nomads/mapper.py` — Update `map_nwps_forecast()` with new field names, add direction conversion, map swell period/direction
3. `pacioos/mapper.py` — Update TODO stub docstrings
4. `nomads_config.py` — Add `GFS_WAVE` to `NOMADSModel` enum
5. Flush stale Redis forecast keys (or wait for TTL expiry)
