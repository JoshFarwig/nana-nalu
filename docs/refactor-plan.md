# Nana Nalu — Public Dashboard Refactor Plan

> Target: Strip the app down to a **public grid-ingest pipeline + MapLibre dashboard**.
> No auth, no accounts, no surf spots. Just ocean data.

---

## Overview

| Phase | Name | Scope |
|---|---|---|
| 0 | Safety Net Fork | Fork to `nana-nalu-pro` before any destruction |
| 1 | Destructive Teardown | Remove all user/account/spot/crew code |
| 2 | Redis → TimescaleDB | Replace Redis forecast cache with time-series DB |
| 3 | Full Grid Ingestion | Ingest all valid grid cells, not nearest-neighbor per spot |
| 4 | NDBC Buoy Workflow | New Prefect flow for buoy ingestion |
| 5 | Public API | No-auth endpoints for grid, point forecast, buoys |
| 6 | Frontend Dashboard | React + shadcn + MapLibre |

---

## Phase 0 — Safety Net Fork

**Before touching a single file**, create the private fork.

```bash
# On GitHub: fork nana-nalu → nana-nalu-pro (private)
# This freezes the full auth/spots/profiles/crew codebase as a future reference
```

**Why:** The `nana-nalu-pro` fork preserves all the existing code if the paid surf tier product is ever revived. Cherry-pick from it later; don't touch it now.

---

## Phase 1 — Destructive Teardown

### Remove Entirely

**Models** (`backend/models/`):
- `user_model.py`
- `account_tier_model.py`
- `condition_profile_model.py`
- `crew_model.py`
- `crew_member_model.py`
- `surf_spot_model.py`

**Repositories** (`backend/repositories/`):
- `user_repository.py`
- `account_tier_repository.py`
- `condition_profile_repository.py`
- `crew_repository.py`
- `surf_spot_repository.py`

**Services** (`backend/services/`):
- `auth_service.py`
- `email_service.py`
- `magic_link_service.py`
- `surf_spot_service.py`
- `crew_service.py`
- `condition_profile_service.py`
- `policies/` (entire directory)

**API Routes** (`backend/api/v1/routes/`):
- `auth.py`
- `users.py`
- `surf_spots.py`
- `crews.py`
- `profiles.py`

**Core** (`backend/core/`):
- `security.py` (JWT, password hashing)
- `templates.py` (email templates)
- `redis.py` (Redis manager — removed in Phase 2)
- `exceptions/auth.py`
- `exceptions/users.py`
- `exceptions/emails.py`
- `exceptions/magic_links.py`
- `exceptions/crews.py`
- `exceptions/condition_profiles.py`
- `exceptions/surf_spots.py`
- `exceptions/account_tiers.py`
- `configs/redis_config.py` (removed in Phase 2)
- `configs/celery_config.py`
- `dependencies/auth.py`

**Templates** (`backend/templates/`):
- All email templates

**Tests** — purge tests for deleted code:
- `unit/core/test_security.py`
- `unit/schemas/test_condition_profile_schema.py`
- `unit/schemas/test_surf_spot_schema.py`
- `unit/services/test_condition_profile_service.py`
- `integration/repositories/test_surf_spot_repo.py`

### Slim `core/config.py`

Remove `WorkerSettings`, `SchedulerSettings` (Celery is dead). Remove `redis` from all remaining settings classes.

```python
# After teardown, config.py has only two service types:
class APISettings(BaseSettings):
    db: DatabaseConfig
    api: APIConfig       # strip JWT, Resend, magic link fields
    http: HTTPConfig

class PrefectSettings(BaseSettings):
    db: DatabaseConfig
    http: HTTPConfig
```

### Slim Docker Compose

Remove services:
- `redis` (Phase 2)
- Any Celery `worker`, `beat`, `flower` services if present in overrides

---

## Phase 2 — Redis → TimescaleDB

### Why TimescaleDB

Redis stored forecasts as JSON blobs with TTL. TimescaleDB gives:
- Structured time-series queries (latest run per model/region, time range slices)
- Built-in retention policies (2-week rolling window — no manual TTL management)
- PostGIS-compatible for spatial nearest-neighbor queries on lat/lon
- Same PostgreSQL driver stack — no new client lib

### Docker: Replace PostGIS with TimescaleDB

The current `db` service uses a custom `Dockerfile.postgis`. Swap it for the official TimescaleDB image which bundles PostGIS:

```yaml
# docker-compose.yml
db:
  image: timescale/timescaledb-ha:pg16
  environment:
    POSTGRES_USER: ${DB__USERNAME}
    POSTGRES_PASSWORD: ${DB__PASSWORD}
    POSTGRES_DB: ${DB__NAME}
```

Remove `redis` service and `redis_data` volume entirely.

### New TimescaleDB Schema

The schema uses **JSONB for all data payloads** — only indexable metadata lives in typed columns. Data enforcement happens at the Pydantic/mapper layer, not the DB column level. This keeps the DB flexible for future models (ROMS currents, WRF winds, etc.) that don't share the same field set.

Two tables. Run metadata lives separately from the 35M-row timeseries.

**`model_runs`** — one row per ingestion batch, the idempotency and coherence anchor:

```sql
CREATE TABLE model_runs (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    provider     TEXT         NOT NULL,
    model        TEXT         NOT NULL,
    region       TEXT         NOT NULL,
    run_time     TIMESTAMPTZ  NOT NULL,  -- model init time; see convention per source below
    ingested_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (provider, model, region, run_time)
);

CREATE INDEX ON model_runs (provider, model, region, ingested_at DESC);
```

**`run_time` convention per data source** — every source provides a non-null timestamp; semantics differ:

| Source | `run_time` value | Source field |
|---|---|---|
| NWPS (GRIB2) | model initialization cycle (`00Z`, `12Z`) | `time` scalar coord |
| ROMS (NetCDF) | forecast window start | `time_coverage_start` global attr |
| Harmonic tides | `date_trunc('day', NOW())` | ingestion date (harmonics have no run cycle) |

No nulls, no special Postgres syntax. Tides use truncated ingestion date — idempotency behavior: second ingest same day hits the unique constraint and is skipped, which is correct.

**`forecast_grid_points`** — one row per `(valid_time, grid_cell)`, grouped by run UUID:

```sql
CREATE TABLE forecast_grid_points (
    time    TIMESTAMPTZ      NOT NULL,  -- valid_time (forecast step)
    run_id  UUID             NOT NULL REFERENCES model_runs(id),
    lat     DOUBLE PRECISION NOT NULL,
    lon     DOUBLE PRECISION NOT NULL,
    data    JSONB            NOT NULL   -- ForecastPoint serialized (exclude_none=True)
);

SELECT create_hypertable('forecast_grid_points', 'time');

CREATE INDEX ON forecast_grid_points (run_id);
CREATE INDEX ON forecast_grid_points USING btree (lat, lon);

SELECT add_retention_policy('forecast_grid_points', INTERVAL '14 days');
```

**Why this split:**

- `provider`, `model`, `region`, `run_time` are no longer repeated across 1.26M rows per run — they live once in `model_runs`
- UUID PK guarantees uniqueness regardless of whether two models share the same `run_time` value
- `ingested_at` gives "latest run" ordering for all sources
- `run_id UUID` on the fact table is the join key, not a search key — the API resolves UUID from `model_runs` first, never scans `forecast_grid_points` by `run_id` directly

**Typical API query pattern:**

```sql
-- Step 1: resolve latest run UUID (model_runs is tiny, fast)
SELECT id FROM model_runs
WHERE provider = $1 AND model = $2 AND region = $3
ORDER BY ingested_at DESC
LIMIT 1;

-- Step 2: fetch grid for that run (or nearest point to lat/lon)
SELECT lat, lon, time, data
FROM forecast_grid_points
WHERE run_id = $resolved_uuid
ORDER BY time ASC;
```

**Idempotency in the pipeline:**

```sql
-- "have we already loaded this run_time for this model+region?"
SELECT 1 FROM model_runs
WHERE provider = $1 AND model = $2 AND region = $3
  AND run_time = $4
LIMIT 1;
-- unique constraint also acts as hard guard on duplicate insert
```

**`buoy_observations`** — NDBC station timeseries (Phase 4), same JSONB pattern:

```sql
CREATE TABLE buoy_observations (
    time        TIMESTAMPTZ      NOT NULL,
    station_id  TEXT             NOT NULL,
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION,
    data        JSONB            NOT NULL   -- BuoyPoint serialized (exclude_none=True)
);

SELECT create_hypertable('buoy_observations', 'time');
CREATE UNIQUE INDEX ON buoy_observations (station_id, time DESC);

SELECT add_retention_policy('buoy_observations', INTERVAL '14 days');
```

### The Enforcement Contract

The DB stores arbitrary JSONB, but the **Pydantic models are the contract**. Data passes through the full mapper → unified schema → JSONB pipeline every time:

```
GRIB2 / NDBC raw data
    ↓  mapper (model-specific)
ForecastPoint (Pydantic, extra="forbid")
    │   wave: WaveData | None
    │   wind: WindData | None
    │   tide: TideData | None
    │   current: CurrentData | None
    ↓  .model_dump_json(exclude_none=True)
JSONB stored in forecast_grid_points.data
    ↓  API read path
ForecastPoint.model_validate(row["data"])   ← re-validated on read
    ↓  response serialization
API response
```

The existing `ForecastPoint` already has `extra="forbid"` and all category fields optional, making it the correct type boundary. ROMS currents would produce:
```json
{"valid_time": "...", "current": {"speed": 0.3, "direction": 180.0}}
```
No `wave`, `wind`, or `tide` keys — stored as-is. The schema doesn't care.

### Internal DTO: `ProviderForecast` → `GridCellForecast`

`ProviderForecast` currently carries `spot_id` and `GridMetadata.distance_km` (nearest-neighbor artifacts from the old pipeline). Replace with a cleaner internal DTO:

```python
# services/forecast/forecast_schema.py — new internal DTO
class GridCellForecast(BaseModel):
    """Internal DTO: complete forecast timeseries for a single grid cell."""
    model_config = ConfigDict(extra="forbid")

    run_uuid: UUID            # FK to model_runs.id — assigned by load task after inserting the run row
    lat: float
    lon: float
    forecast: list[ForecastPoint]

    def to_db_rows(self) -> list[dict]:
        """Expand timeseries into individual DB rows for bulk insert."""
        return [
            {
                "time":    point.valid_time,
                "run_id":  self.run_uuid,
                "lat":     self.lat,
                "lon":     self.lon,
                "data":    point.model_dump(exclude_none=True, mode="json"),
            }
            for point in self.forecast
        ]
```

The load task flow:
1. `INSERT INTO model_runs (...) RETURNING id` → get the UUID
2. Attach UUID to each `GridCellForecast`
3. Bulk insert all rows into `forecast_grid_points`

`provider`, `model`, `region`, `run_time` are no longer fields on the DTO — they live in `model_runs` and don't need to travel with each grid cell.

`ProviderForecast` (with `spot_id`) stays in the codebase but becomes a private detail of the `nana-nalu-pro` fork. The public repo uses `GridCellForecast` going forward.

### Row Volume Estimate

Maui CG4 at ~500m resolution over the bbox: ~15k valid ocean cells.
NWPS hourly timesteps for 7 days: ~84 steps.
Per run: `15,000 × 84 = ~1.26M rows`
With 2 runs/day × 14 days retention: **~35M rows**.

TimescaleDB handles this comfortably at this scale. Chunks partition by time automatically.

### Idempotency Without Redis

Currently `get_last_run_time()` reads from Redis to skip already-processed runs. Replace with a `model_runs` query — the table is small and fast:

```sql
-- "Have we already loaded this run_time for this model+region?"
SELECT 1 FROM model_runs
WHERE provider = $1 AND model = $2 AND region = $3
  AND run_time = $4
LIMIT 1;
```

Single query, no special cases. Each source computes its `run_time` before checking — NWPS uses the GRIB2 `time` coord, ROMS uses `time_coverage_start`, tides use `date_trunc('day', NOW())`. The `UNIQUE (provider, model, region, run_time)` constraint also acts as a hard guard — a duplicate insert will raise a conflict rather than silently loading twice.

---

## Phase 3 — Full Grid Ingestion

### The Core Shift

**Before:** query surf spots in bbox → NN search per spot → extract per-spot timeseries → store per `spot_id`

**After:** open GRIB2 → filter all valid ocean cells → store entire grid → NN done at query time by the API

### What Changes in the NWPS Flow

**`extract.py`** — remove `SurfSpotRepository` dependency entirely. Instead of extracting per spot, collect all valid (non-NaN) grid cells:

```python
# Before: builds KDTree, queries per spot
spots = repo.get_all_in_grid(...)
selected_lats, selected_lons, distances = query_nearest_forecast_points(...)

# After: collect all valid ocean cells from the dataset
valid_mask = ~np.isnan(ds['swh'].values[0])  # use first timestep as land mask
valid_lats = ds.latitude.values[valid_mask]
valid_lons = ds.longitude.values[valid_mask]
# build list of (lat, lon, timeseries) for all valid cells
```

**`transform.py`** — mapper produces `GridCellForecast` (replacing `ProviderForecast`) per cell. Each cell's `ForecastPoint` list is validated through the existing unified schema — `WaveData`, `WindData`, `TideData`, `CurrentData` — before storage. No `spot_id`, no `distance_km`.

**`load.py`** — calls `cell.to_db_rows()` on each `GridCellForecast`, flattening all cells × all timesteps into a single list of dicts, then bulk-inserts via `execute_many` or `COPY`. One row per `(time, lat, lon, model, region, run_id)`, data stored as JSONB.

**`flow.py`** — remove `process_region_forecast`'s dependency on DB for spots. The flow stays region-scoped but no longer iterates per-spot:
- Check last run (DB query replacing Redis)
- Download GRIB2
- Extract all valid cells
- Transform to rows
- Bulk insert to TimescaleDB
- Cleanup

### Config: `NWPSConfig` stays Pydantic

`NWPSConfig` / `MauiNWPSConfig` is already well-structured. Remove only:
- `max_nearest_neighbor_distance_km` (NN is now a DB/API concern, not an ingestion concern)
- Keep `grid` bounds — still needed to scope the GRIB2 subregion download

Future Maui County expansion (Molokai, Molokini): add `Region.MAUI_COUNTY` with wider `RegionGrid` and a corresponding `MauiCountyNWPSConfig` entry in the registry. No structural change needed.

### `workflows/resources.py`

Remove `SyncRedisManager`. `ForecastResources` keeps only `http`, `db`, `settings`.

---

## Phase 4 — NDBC Buoy Workflow

### Station Config: Pydantic (not DB)

Buoy stations are static, infrequently added, and code-versioned is fine. Pydantic mirrors the existing `NWPSConfig` pattern. Move to DB only if operators need runtime config (future B2B concern).

```python
# backend/workflows/ndbc/buoy_config.py

class BuoyStation(BaseModel):
    model_config = ConfigDict(frozen=True)

    station_id: str       # NDBC station ID e.g. "51202"
    name: str             # human label e.g. "Pauwela"
    lat: float
    lon: float
    region: Region

class NDBCConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str = "https://www.ndbc.noaa.gov/data/realtime2"
    fetch_interval_hours: int = 1
    lookback_hours: int = 48  # how far back to ingest on cold start

# Station registry (analogous to NOMADS_CONFIG_REGISTRY)
BUOY_STATIONS: dict[str, BuoyStation] = {
    "51202": BuoyStation(station_id="51202", name="Pauwela",  lat=21.017, lon=-156.422, region=Region.MAUI),
    "51201": BuoyStation(station_id="51201", name="Waimea",   lat=21.673, lon=-158.116, region=Region.MAUI),
    "51204": BuoyStation(station_id="51204", name="Mokapu",   lat=21.417, lon=-157.668, region=Region.MAUI),
}
```

### Buoy Flow Structure

Mirror the NWPS flow pattern:
```
workflows/ndbc/
    buoy_config.py
    flow.py              # orchestrate_buoy_ingestion()
    tasks/
        download.py      # fetch .txt from NDBC realtime2
        parse.py         # parse fixed-width NDBC format
        load.py          # bulk insert to buoy_observations
```

NDBC realtime format is fixed-width `.txt` — parse with `pandas.read_fwf` or manual column splits. Filter rows older than `lookback_hours`. Idempotency: `ON CONFLICT (time, station_id) DO NOTHING` (unique index already defined on the table).

**`BuoyPoint`** — buoy equivalent of `ForecastPoint`. Same JSONB pattern: enforced by Pydantic, stored generically:

```python
# services/forecast/forecast_schema.py — add alongside ForecastPoint
class BuoyPoint(BaseModel):
    """Single buoy observation at a point in time."""
    model_config = ConfigDict(extra="forbid")

    time: datetime

    # spectral wave (from NDBC standard met + spectral files)
    wvht: float | None = Field(default=None, description="Significant wave height (m)")
    dpd:  float | None = Field(default=None, description="Dominant period (s)")
    apd:  float | None = Field(default=None, description="Average period (s)")
    mwd:  float | None = Field(default=None, description="Mean wave direction (deg from)")

    # met
    wspd: float | None = Field(default=None, description="Wind speed (m/s)")
    wdir: float | None = Field(default=None, description="Wind direction (deg from)")
    gst:  float | None = Field(default=None, description="Wind gust (m/s)")
    atmp: float | None = Field(default=None, description="Air temperature (°C)")
    wtmp: float | None = Field(default=None, description="Water temperature (°C)")
    pres: float | None = Field(default=None, description="Atmospheric pressure (hPa)")
```

Buoy mapper produces `BuoyPoint` objects, serializes to JSONB with `exclude_none=True`, same pipeline as forecast grid. API re-validates on read with `BuoyPoint.model_validate(row["data"])`.

---

## Phase 5 — Public API

No auth middleware on any routes. Remove `dependencies/auth.py` usage from startup.

### New Route Structure

```
api/v1/routes/
    grid.py      # GET /grid/{model}/{region}  — latest run full grid (for map heatmap)
    forecast.py  # GET /forecast?lat=&lon=&model= — point forecast via NN query
    buoys.py     # GET /buoys  — station list + latest obs
    health.py    # GET /health
```

### `GET /grid/{model}/{region}`

Returns the latest run's grid cells for a model/region. Used by the map to paint a heatmap or vector tiles. Supports optional `?field=swh` query param to scope which variable to return.

```sql
SELECT lat, lon, swh, perpw, dirpw, wind_speed, wind_dir, zos
FROM forecast_grid_points
WHERE model = $1 AND region = $2
  AND run_id = (
      SELECT MAX(run_id) FROM forecast_grid_points
      WHERE model = $1 AND region = $2
  )
ORDER BY time ASC
```

Response: `{ run_id, model, region, grid: [{ lat, lon, time, data: ForecastPoint }, ...] }`

The API reads raw JSONB rows and re-validates through `ForecastPoint.model_validate(row["data"])` before serializing. This means the API response shape is always governed by the Pydantic schema, even if the stored JSONB has unexpected fields from a future model.

### `GET /forecast?lat=&lon=&model=`

On-demand point forecast: find the nearest grid cell to the requested lat/lon, return full time-series for the latest run. This is where NN lives now — in the API, not ingestion.

```sql
-- nearest neighbor via Euclidean approx (fast, sufficient at this scale)
SELECT DISTINCT ON (time) lat, lon, time, swh, perpw, dirpw, wind_speed, wind_dir, zos,
  ((lat - $1)^2 + (lon - $2)^2) AS dist
FROM forecast_grid_points
WHERE model = $3
  AND run_id = (SELECT MAX(run_id) FROM forecast_grid_points WHERE model = $3)
ORDER BY time ASC, dist ASC
```

Response: `{ lat, lon, model, run_id, forecast: [{ time, wave, wind, tide }, ...] }`

> **Note on spatial precision:** Euclidean distance works fine at Maui's scale (~50km bbox). If coverage expands significantly, swap to `ST_Distance` with PostGIS geography type.

### `GET /buoys`

Returns all configured stations with their latest observation.

### `APIConfig` after teardown

Remove: `JWT_SECRET_KEY`, `RESEND_API_KEY`, `ADMIN_EMAIL`, `APP_URL`, magic link fields.
Keep: `ADMIN_USERNAME`, `ADMIN_PASSWORD` (for a basic /admin health check if needed), `PORT`.

---

## Phase 6 — Frontend Dashboard

Stack: **React + shadcn/ui + MapLibre GL JS + TanStack Query**

### Architecture

```
frontend/src/
    components/
        map/
            MapView.tsx          # MapLibre canvas, primary surface
            ForecastLayer.tsx    # renders grid data as heatmap/fill-extrusion
            BuoyMarkers.tsx      # NDBC station pins
        nav/
            ModelSelector.tsx    # toggle NWPS / GFS-Wave / etc.
            LayerSelector.tsx    # toggle field: swell, wind, tide
        sidebar/
            PointForecast.tsx    # 7-day forecast panel on map click
            BuoyDetail.tsx       # buoy obs detail panel
    hooks/
        useGrid.ts               # fetches /grid/{model}/{region}
        usePointForecast.ts      # fetches /forecast?lat=&lon=
        useBuoys.ts              # fetches /buoys
    lib/
        api.ts                   # typed API client
```

### Map Interaction Model

1. **Default view:** map loads with latest NWPS swell height grid as a color-ramp layer.
2. **Navbar:** model toggle (NWPS / GFS-Wave) + field toggle (swh / wind / tide).
3. **Click on map:** fires `GET /forecast?lat=&lon=&model=` with clicked coords → opens sidebar with 7+ day forecast.
4. **Buoy pins:** always visible, click opens buoy detail panel.

### Grid Visualization Approach

Two options — decide based on data density:
- **Option A (simple):** GeoJSON `FeatureCollection` of points, rendered as `circle` layer with `circle-color` expression on `swh`. Works fine for < 50k points.
- **Option B (performant):** Pre-render grid to a PNG tile on the backend, serve as raster tiles. Better for large grids or mobile.

Start with Option A. The Maui NWPS CG4 grid at ~500m resolution over the island bbox is roughly `(0.49° lat / 0.005°) × (0.77° lon / 0.005°)` ≈ `98 × 154` ≈ **15k cells**. Option A handles this trivially.

---

## Open Questions / Decisions

### 1. Is Redis fully gone?

Prefect replaces Celery (broker use-case). Forecast cache moves to TimescaleDB. Idempotency moves to DB query. **Yes, Redis is fully gone.** No remaining use case.

### 2. Buoy config: Pydantic (recommended) vs DB

**Recommendation: Pydantic.** Matches existing `NWPSConfig` pattern. Stations are static. DB-backed config adds operational overhead (migration to add a station) with no benefit until you need runtime configurability (i.e., operator self-service for B2B). Revisit when forking for marine B2B.

### 3. Alembic migrations

The existing Alembic setup targets PostgreSQL/PostGIS. TimescaleDB is PostgreSQL-compatible, but:
- `create_hypertable()` and `add_retention_policy()` are TimescaleDB-specific functions — they go in a raw SQL migration, not standard Alembic `op.*` calls.
- Strategy: write a single Alembic migration that drops all old tables and creates new TimescaleDB schema via `op.execute()`.

### 4. GFS-Wave as second model

The `NOMADSModel.GFS_WAVE` enum already exists but has no config implementation. Leave as a stub for now; the architecture supports adding it by adding a config class + registry entry.

---

## What Stays (Unchanged or Lightly Modified)

| Component | Status |
|---|---|
| `workflows/nomads/nwps/tasks/download.py` | Keep — GRIB2 download logic is independent |
| `workflows/nomads/nwps/tasks/availability.py` | Keep — NOMADS polling logic unchanged |
| `workflows/nomads/nwps/tasks/extract_sub_tasks.py` | Keep — `open_grib`, `build_kdtree` reused |
| `workflows/pacioos/tide_mhi/` | Keep — tide MHI workflow unrelated to auth |
| `core/logging/` | Keep — logging config untouched |
| `core/database.py` | Keep — SQLAlchemy managers, swap connection URL |
| `core/http.py` | Keep — HTTP manager |
| `utils/geo_spatial.py` | Keep — `query_nearest_forecast_points` reused in API |
| `utils/region.py` | Keep — `Region`, `RegionGrid` stay |
| `utils/geo_validation.py` | Keep |
| `services/forecast/nomads_config.py` | Modify — remove `max_nearest_neighbor_distance_km` |
| `prefect.yaml` | Modify — remove Redis-dependent deployments |
| `docker-compose.yml` | Modify — swap DB image, remove Redis service |

---

## Build Order for Subagents

Phases have hard dependencies. Suggested agent breakdown:

```
Phase 0:  [human] — fork on GitHub
Phase 1:  agent-teardown        — delete files, slim config, update imports
Phase 2a: agent-timescale-db    — new DB image, schema migrations, update DB manager
Phase 2b: agent-redis-removal   — remove Redis from config, resources, docker-compose
Phase 3:  agent-grid-ingest     — rewrite extract/transform/load for full grid
Phase 4:  agent-buoy-workflow   — new NDBC flow
Phase 5:  agent-api             — new public routes
Phase 6:  agent-frontend        — React dashboard (separate repo or frontend/)
```

Phases 2a and 2b can run in parallel. Phase 3 depends on 2a (new schema). Phase 5 depends on 3 + 4.
