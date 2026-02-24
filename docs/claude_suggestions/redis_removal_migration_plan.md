# Forecast Data Migration Plan: Redis → PostgreSQL (TimescaleDB)

## Overview

Migrate forecast storage from Redis to PostgreSQL with TimescaleDB, creating a persistent, queryable historical archive of forecast data. Redis remains in the stack for what it does best — ephemeral TTL-based auth tokens and magic links.

**Architecture after migration:**

| Store | Responsibility |
|-------|---------------|
| **Redis** | Auth refresh tokens, session tracking, magic links (unchanged) |
| **PostgreSQL + TimescaleDB** | Forecast time-series data (historical + current), condition profile evaluation |
| **TanStack Query** | Client-side forecast caching (5-15 min staleTime) |

**Why this migration:**
- Forecast data becomes queryable via SQL (historical trends, condition profile scoring)
- TimescaleDB compression gives 90%+ storage reduction on older data
- Enables features that require historical lookups (forecast accuracy tracking, trend analysis)
- Redis stays lean — only ephemeral tokens (~100MB footprint)

---

## Phase 1: TimescaleDB Setup

### 1.1 Docker Image Swap

**`db/Dockerfile.postgis`** → **`db/Dockerfile.timescaledb`** (rename)

Replace the current PostGIS Dockerfile:

```dockerfile
# TimescaleDB HA image includes PostGIS out of the box
FROM timescale/timescaledb-ha:pg17
```

> **Note:** TimescaleDB HA currently supports up to PostgreSQL 17. The current setup uses PostgreSQL 18. This means either:
> - Downgrade to pg17 (recommended — TimescaleDB + PostGIS combo is worth it)
> - Wait for TimescaleDB pg18 support
> - Use pg18 with manual TimescaleDB extension install (less straightforward)
>
> The `timescaledb-ha` image includes: PostgreSQL, TimescaleDB, PostGIS, and other extensions.

Update `docker-compose.yml` db service:

```yaml
db:
  build:
    context: ./db
    dockerfile: Dockerfile.timescaledb
```

Add to `db/init/` a script to enable extensions:

```sql
-- 01_extensions.sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### 1.2 New Database Model

**File:** `backend/models/forecast_point_model.py` (new)

```python
class ForecastPoint(Base):
    __tablename__ = "forecast_points"

    # Composite primary key matching the TimescaleDB hypertable time dimension
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    spot_id: Mapped[int] = mapped_column(
        ForeignKey("surf_spots.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    model: Mapped[str] = mapped_column(String(30), primary_key=True)

    # Metadata
    analysis_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    region: Mapped[str] = mapped_column(String(50))
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Forecast data as JSONB (mirrors existing ProviderForecast.ForecastPoint structure)
    wave: Mapped[dict | None] = mapped_column(JSONB)
    wind: Mapped[dict | None] = mapped_column(JSONB)
    tide: Mapped[dict | None] = mapped_column(JSONB)
    current: Mapped[dict | None] = mapped_column(JSONB)

    spot: Mapped["SurfSpot"] = relationship()
```

### 1.3 Alembic Migration

The migration needs to:
1. Create the `forecast_points` table
2. Convert it to a TimescaleDB hypertable
3. Create the `forecast_runs` metadata table (replaces `last_run` Redis keys)
4. Add appropriate indices

```python
def upgrade():
    # Create forecast_points table
    op.create_table("forecast_points", ...)

    # Convert to hypertable (raw SQL — TimescaleDB extension)
    op.execute(
        "SELECT create_hypertable('forecast_points', 'time', "
        "partitioning_column => 'spot_id', number_partitions => 4)"
    )

    # Create forecast_runs for idempotency tracking (replaces last_run Redis keys)
    op.create_table(
        "forecast_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(30), nullable=False),
        sa.Column("region", sa.String(50), nullable=False),
        sa.Column("run_id", sa.String, nullable=False),  # ISO timestamp string
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "model", "region"),
    )

    # Index for the common query pattern: current forecast for a spot
    op.create_index(
        "ix_forecast_points_spot_provider_model_time",
        "forecast_points",
        ["spot_id", "provider", "model", "time"],
    )
```

---

## Phase 2: Forecast Repository + Service Migration

### 2.1 New Repository

**File:** `backend/repositories/forecast_repository.py` (new)

Two repository classes following existing repository patterns:

**`AsyncForecastRepository`** (for FastAPI/API reads):
- `get_current_forecast(spot_id, provider, model)` → list of ForecastPoint rows for latest analysis_time
- `get_all_current_forecasts(spot_id)` → all provider/model forecasts for a spot (latest only)
- `get_nearest_point(spot_id, provider, model, target_time)` → single closest forecast point to a time
- `get_available_providers(spot_id)` → distinct provider/model combos with data
- `get_historical(spot_id, provider, model, start, end)` → forecast points within time range

**`SyncForecastRepository`** (for Prefect workers):
- `bulk_upsert(points: list[ForecastPoint])` — INSERT ... ON CONFLICT (time, spot_id, provider, model) DO UPDATE
- `get_last_run(provider, model, region)` → run_id string or None
- `set_last_run(provider, model, region, run_id)` — UPSERT into forecast_runs

### 2.2 Workflow Load Task Changes

**`backend/workflows/nomads/nwps/tasks/load.py`:**

Replace Redis pipeline writes with database bulk insert. Redis continues to receive forecast data for fast current-forecast reads.

```python
@task(name="nwps-load", retries=2, retry_delay_seconds=10)
def load(forecasts: dict[int, ProviderForecast], region: str, run_id: str) -> int:
    resources = get_resources()
    db = resources.db
    redis = resources.redis

    # 1. Write to PostgreSQL (persistent archive)
    with db.session() as session:
        repo = SyncForecastRepository(session)

        rows = []
        for spot_id, provider_forecast in forecasts.items():
            for point in provider_forecast.forecast_points:
                rows.append(ForecastPoint(
                    time=point.time,
                    spot_id=spot_id,
                    provider=provider_forecast.provider,
                    model=provider_forecast.model,
                    region=region,
                    analysis_time=provider_forecast.analysis_time,
                    wave=point.wave.model_dump(exclude_none=True) if point.wave else None,
                    wind=point.wind.model_dump(exclude_none=True) if point.wind else None,
                    tide=point.tide.model_dump(exclude_none=True) if point.tide else None,
                    current=point.current.model_dump(exclude_none=True) if point.current else None,
                ))

        repo.bulk_upsert(rows)
        repo.set_last_run("nomads", "nwps", region, run_id)
        session.commit()

    # 2. Write to Redis (fast current-forecast cache — existing behavior)
    with redis.pipeline() as pipe:
        for spot_id, provider_forecast in forecasts.items():
            key = f"forecast:nomads:nwps:{region}:{spot_id}"
            pipe.setex(key, timedelta(hours=14), provider_forecast.to_redis_json())
        pipe.set(f"forecast:nomads:nwps:{region}:last_run", run_id)
        pipe.execute()

    return len(forecasts)
```

Same dual-write pattern for `backend/workflows/pacioos/tide_mhi/tasks/load.py`.

> **Design note:** The dual-write approach means the API can continue reading from Redis for current forecasts (zero latency regression), while PostgreSQL accumulates the historical archive. The ForecastService can be updated later to read from PostgreSQL if desired, or Redis can remain the primary read path for current data.

### 2.3 ForecastService Changes

**`backend/services/forecast/forecast_service.py`:**

Add `forecast_repo` as a **second** dependency alongside existing `redis_manager`:

- Constructor: Add `forecast_repo: AsyncForecastRepository` parameter
- Existing methods (`get_forecasts`, etc.): **Keep reading from Redis** for current forecasts — no change needed
- New methods for historical/queryable access:
  - `get_historical_forecast(spot_id, provider, model, start, end)` → query PostgreSQL
  - `get_nearest_forecast_point(spot_id, provider, model, target_time)` → query PostgreSQL

> **Optional future step:** If you decide Redis is redundant for forecast reads, swap the read path to PostgreSQL and stop writing forecasts to Redis. This is a clean cutover since the data shapes are identical.

### 2.4 ForecastSchema Changes

**`backend/services/forecast/forecast_schema.py`:**

- Keep `to_redis_json()` and `from_redis_json()` — Redis remains the current-forecast read path
- Add `from_db_rows(rows)` classmethod to reconstruct `ProviderForecast` from forecast_point rows (for historical queries)
- Add `to_db_rows(spot_id, region)` for the load step

### 2.5 Dependency Injection Updates

**`backend/core/dependencies/services.py`:**
- `get_forecast_service()`: Add `forecast_repo` alongside existing `redis_manager`

---

## Phase 3: Data Lifecycle + Compression

### 3.1 TimescaleDB Compression Policy

Enable automatic compression for historical data:

```sql
-- Compress chunks older than 7 days (data is still queryable, just compressed)
ALTER TABLE forecast_points SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'spot_id, provider, model',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('forecast_points', compress_after => INTERVAL '7 days');
```

This gives 90%+ compression on older forecast data with zero application changes.

### 3.2 Retention Policy

Choose a retention window based on storage budget:

**Option A — TimescaleDB `drop_chunks()` (recommended):**
```sql
-- Automatically drop data older than 90 days
SELECT add_retention_policy('forecast_points', drop_after => INTERVAL '90 days');
```

**Option B — Prefect scheduled task:**
```python
@flow(name="forecast-data-cleanup")
def cleanup_old_forecasts():
    # For manual control over retention
    session.execute(text(
        "SELECT drop_chunks('forecast_points', older_than => INTERVAL '90 days')"
    ))
```

### 3.3 Storage Estimates (Oracle ARM Free Tier)

For ~20 spots, 2 providers, ~70 forecast points per run, 2 runs/day:

| Timeframe | Uncompressed | Compressed (~10:1) |
|-----------|-------------|-------------------|
| 1 day | ~5 MB | ~0.5 MB |
| 30 days | ~150 MB | ~15 MB |
| 90 days | ~450 MB | ~45 MB |
| 1 year | ~1.8 GB | ~180 MB |

Well within Oracle free tier limits. TimescaleDB compression is the key — without it, a year of data would be significant. With it, it's trivial.

---

## Phase 4: Condition Profile Evaluation (Unlocked by Phase 2)

With forecast data in PostgreSQL, condition profile evaluation can query directly:

```python
async def evaluate_all_viewable_condition_profiles(self, user_id: int):
    viewable_spots = await self.spot_repo.get_all_user_viewable_spots(user_id)
    spot_ids = {spot.id for spot in viewable_spots}
    profiles = await self.profile_repo.get_all_for_spot_ids(spot_ids)

    profiles_by_spot = defaultdict(list)
    for profile in profiles:
        profiles_by_spot[profile.spot_id].append(profile)

    for spot_id, spot_profiles in profiles_by_spot.items():
        # Collect unique provider:model combos needed
        required = {
            (entry.provider, entry.model)
            for profile in spot_profiles
            for entry in profile.conditions
        }

        # Single DB query: get nearest forecast point for each provider:model
        forecasts = {}
        for provider, model in required:
            point = await self.forecast_repo.get_nearest_point(
                spot_id, provider, model, target_time=datetime.now(timezone.utc)
            )
            if point:
                forecasts[(provider, model)] = point

        # Evaluate each profile against the forecast data
        # ... (evaluation logic)
```

This also enables future features like:
- "Was this condition profile satisfied in the last 7 days?" (historical query)
- Forecast accuracy tracking (compare predicted vs observed)
- Trend visualization ("swell height over the past month at Pipeline")

---

## File Change Summary

| Action | File | Phase |
|--------|------|-------|
| **Rename** | `db/Dockerfile.postgis` → `db/Dockerfile.timescaledb` | 1 |
| **New** | `db/init/01_extensions.sql` | 1 |
| **New** | `backend/models/forecast_point_model.py` | 1 |
| **New** | Alembic migration (forecast_points + forecast_runs) | 1 |
| **New** | `backend/repositories/forecast_repository.py` | 2 |
| **Modify** | `backend/workflows/nomads/nwps/tasks/load.py` | 2 |
| **Modify** | `backend/workflows/pacioos/tide_mhi/tasks/load.py` | 2 |
| **Modify** | `backend/services/forecast/forecast_service.py` | 2 |
| **Modify** | `backend/services/forecast/forecast_schema.py` | 2 |
| **Modify** | `backend/core/dependencies/services.py` | 2 |
| **Modify** | `docker-compose.yml` (db service dockerfile ref) | 1 |

**Files NOT changed (Redis stays):**
- `backend/core/redis.py` — unchanged
- `backend/core/configs/redis_config.py` — unchanged
- `backend/services/auth_service.py` — unchanged
- `backend/services/magic_link_service.py` — unchanged
- `backend/workflows/resources.py` — keeps Redis in ForecastResources
- `redis/Dockerfile.redis` — unchanged
- Docker Compose redis service — unchanged

---

## Migration Order & Risk

**Recommended order:** Phase 1 → Phase 2 → Phase 3 → Phase 4

Phase 1 is infrastructure-only (no application code changes besides the model/migration). Phase 2 introduces the dual-write pattern — Redis continues serving current forecasts, PostgreSQL accumulates history. This is zero-risk to existing functionality.

**Data migration:** None needed. PostgreSQL starts empty and accumulates data from the next workflow run onward. Historical data begins building immediately.

**Rollback strategy:** Since Redis remains the primary read path for current forecasts, rolling back Phase 2 means simply removing the PostgreSQL write from the load tasks. No data loss, no user impact.

**pg18 → pg17 consideration:** The TimescaleDB HA image currently targets pg17. This requires a database migration (pg_dump/pg_restore) since you're on pg18. Alternatively, install TimescaleDB manually on pg18 if you want to stay on the latest PostgreSQL version. The HA image is simpler for getting started.

---

## Key Decisions to Make Before Starting

1. **pg17 (TimescaleDB HA image) vs pg18 (manual TimescaleDB install)?**
   - pg17 with `timescaledb-ha` is the path of least resistance
   - pg18 keeps you on latest PostgreSQL but requires manual extension management

2. **Retention window:** How far back do you want historical forecast data? 30 days, 90 days, 1 year? (Configurable via TimescaleDB retention policy, easy to change later)

3. **Dual-write vs full cutover:** The plan uses dual-write (Redis + PostgreSQL). Later, you can optionally stop writing to Redis and read forecasts from PostgreSQL only. This is a future optimization, not a requirement.
