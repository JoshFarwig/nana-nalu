# Test Implementation Plan

## Architecture & Testing Philosophy

### How This Codebase Uses Routes vs Services

This project has **two route patterns**:

1. **Route → Repo (direct)**: Simple CRUD with no business logic. The route injects a session, creates a repo, calls one method, wraps the response. Examples: `users.py` (`get_by_id`, `update_profile`), `surf_spots.py` (`get_all_with_coordinates`, `get_with_coordinates`).

2. **Route → Service → Repo**: Multi-step operations with validation, authorization, or cross-repo coordination. Examples: `crews.py` (quota checks + repo calls), `condition_profiles.py` (forecast evaluation across providers + profile matching).

This is a **pragmatic split** — routes that only need a single repo call skip the service layer, avoiding unnecessary DI overhead. Routes that need business logic go through services.

### What This Means for Testing

**Don't test the route layer in isolation.** Here's why:

- Route → Repo direct calls are just `repo.method()` + `SuccessResponse(...)`. There's no logic to get wrong. If the repo works and Pydantic validates, the route works.
- Route → Service calls are also thin — they extract `current_user`, call `service.method()`, wrap the result. Same thing.
- Testing routes with mocked services/repos proves nothing. You're testing that FastAPI dependency injection works, which it does.

**Instead, test where bugs actually hide:**

| Layer | Has testable logic? | Test approach |
|-------|-------------------|---------------|
| **Range helpers** (`in_range`, `direction_in_range`) | Yes — boundary conditions, None handling, north-wrapping | Unit test (pure functions) |
| **Service matching** (`_entry_matches`, `_evaluate_profile`) | Yes — AND logic, missing data, JSONB deserialization | Unit test (construct service with `None` deps) |
| **Schema validation** (Pydantic validators) | Yes — min>max rejection, duplicate providers, required fields | Unit test (construct schemas directly) |
| **Workflow transforms** (mapper + transform tasks) | Yes — data parsing, unit conversion, grid selection | Unit test (feed raw data, check output) |
| **Repo queries** (complex JOINs, filters) | Yes — `get_all_viewable_for_user` has crew membership logic | Integration test (real DB) |
| **Service orchestration** (evaluation pipeline) | Yes — concurrent fetches, forecast lookup, batch results | Integration test (real DB + Redis) |
| **Routes** | No — just glue | Covered by integration tests or skip entirely |

### Practical Testing Rules

1. **Unit test pure logic** — if it takes data in and returns data out with no I/O, unit test it
2. **Integration test the seams** — where repos, services, and external stores (DB, Redis) interact
3. **Don't mock what you own** — mocking your own repos/services in route tests is low-value busywork. Test the real thing via integration tests
4. **Test behavior, not implementation** — "profile with wave height 2.1m matches range 1-3m" not "in_range called with args (2.1, RangeCondition(...))"
5. **One test per edge case, not per line of code** — direction wrapping needs 4 tests, not 20

---

## Tier 1: Unit Tests (CI / GitHub Actions)

**No external services. No Docker. Runs in seconds.**

Marker: `@pytest.mark.unit`

### File: `tests/unit/conftest.py`

Shared fixtures for constructing test data:

- `make_forecast_point(wave=, wind=, tide=)` — factory for `ForecastPoint` with optional overrides
- `make_swell(height=, period=, direction=)` — factory for `SwellPartition` dicts
- `typical_wave_point` — realistic Maui north shore ForecastPoint (sig_height=2.1m, peak_period=14s, primary_swell NW, wind=5.5m/s NE, tide=0.3m)
- `mock_profile(spot_id, conditions)` — lightweight fake that quacks like `ConditionProfile` ORM model (avoids DB dependency)
- `service` — bare `ConditionProfileService(None, None, None, None)` for testing pure methods

### File: `tests/unit/test_condition_matching.py`

#### `TestInRange` (~8 tests)

| Test | What it verifies |
|------|-----------------|
| `test_value_within_range` | Basic happy path |
| `test_value_at_min_boundary` | `value == min` → True |
| `test_value_at_max_boundary` | `value == max` → True |
| `test_value_below_min` | Below range → False |
| `test_value_above_max` | Above range → False |
| `test_none_value_always_false` | `None` input → False (forecast data missing) |
| `test_min_only` / `test_max_only` | One-sided bounds work |
| `test_exact_value` | `min == max` → only exact match |

#### `TestDirectionInRange` (~8 tests)

| Test | What it verifies |
|------|-----------------|
| `test_normal_range` | Standard range (90°→270°) |
| `test_outside_normal_range` | Value outside standard range |
| `test_none_value_always_false` | `None` input |
| `test_min_only_direction` / `test_max_only_direction` | One-sided bounds |
| `test_north_wrap_inside_high_side` | 350° in 330°→030° → True |
| `test_north_wrap_inside_low_side` | 10° in 330°→030° → True |
| `test_north_wrap_outside` | 180° in 330°→030° → False |
| `test_north_wrap_boundary` | Exactly at min/max of wrapping range |

#### `TestEntryMatches` (~10 tests)

| Test | What it verifies |
|------|-----------------|
| `test_wave_height_in_range` | Single wave field matches |
| `test_wave_height_out_of_range` | Single wave field misses |
| `test_wind_speed_in_range` / `out_of_range` | Wind matching |
| `test_tide_height_in_range` | Tide matching |
| `test_multiple_conditions_all_must_match` | AND logic: wave OK + wind miss → False |
| `test_multiple_conditions_all_match` | AND logic: everything OK → True |
| `test_wave_condition_but_no_wave_data` | Entry expects wave, forecast has none → False |
| `test_primary_swell_matches` | Swell partition matching |
| `test_primary_swell_missing_from_forecast` | Entry expects swell, forecast has none → False |
| `test_secondary_swell_out_of_range` | Secondary swell value misses |

#### `TestEvaluateProfile` (~5 tests)

| Test | What it verifies |
|------|-----------------|
| `test_single_entry_matches` | One provider entry, matches forecast lookup |
| `test_missing_forecast_data_returns_false` | Provider key not in lookup → False |
| `test_and_across_providers` | Two providers (NWPS + tide) both match → True |
| `test_and_across_providers_one_fails` | Two providers, one misses → False |
| `test_none_forecast_point_in_lookup` | Key exists but value is None (Redis miss) → False |

### File: `tests/unit/test_condition_schema.py`

Pydantic validation edge cases — tests that schemas reject invalid input correctly.

| Test | What it verifies |
|------|-----------------|
| `test_range_condition_requires_at_least_one_bound` | `RangeCondition()` with no min/max raises |
| `test_entry_requires_at_least_one_category` | `ProviderConditionEntry(provider=..., model=...)` with no wave/wind/tide raises |
| `test_non_direction_min_gt_max_rejected` | `significant_height(min=10, max=5)` raises |
| `test_direction_min_gt_max_allowed` | `peak_direction(min=330, max=30)` is valid (wrapping) |
| `test_duplicate_provider_model_rejected` | Two entries with same provider+model raises |
| `test_create_requires_at_least_one_entry` | Empty conditions list raises |
| `test_update_null_conditions_rejected` | `conditions=None` or `conditions=[]` raises |
| `test_valid_full_profile_create` | Happy path with realistic multi-provider profile |

### File: `tests/unit/test_forecast_schema.py`

Serialization round-trip tests — ensures Redis storage doesn't lose data.

| Test | What it verifies |
|------|-----------------|
| `test_provider_forecast_redis_roundtrip` | `to_redis_json()` → `from_redis_json()` preserves all fields |
| `test_redis_json_excludes_none` | Serialized JSON doesn't contain null fields |
| `test_forecast_point_optional_categories` | Point with only wave (no wind/tide) roundtrips correctly |
| `test_swell_partitions_roundtrip` | Primary/secondary/tertiary swells survive serialization |

### File: `tests/unit/test_workflow_transform.py`

Transform task and mapper logic — pure data processing.

| Test | What it verifies |
|------|-----------------|
| `test_nomads_mapper_wave_fields` | NOMADS raw data → WaveData mapping |
| `test_nomads_mapper_swell_partitions` | Swell partition extraction from GRIB fields |
| `test_pacioos_mapper_tide_fields` | PacIOOS tide data → TideData mapping |
| `test_transform_produces_forecast_points` | Full transform output has correct ForecastPoint structure |
| `test_transform_handles_missing_variables` | Graceful handling when model output lacks optional fields |

---

## Tier 2: Integration Tests (Local Dev / Pre-Release)

**Requires `docker-compose.test.yml` (DB + Redis on test ports).**

Marker: `@pytest.mark.integration`

### File: `tests/integration/conftest.py`

Fresh fixtures (not reusing old conftest patterns):

```
Fixtures needed:
- async_engine         (session-scoped) — create tables once
- async_session        (function-scoped) — SAVEPOINT + rollback per test
- async_redis          (function-scoped) — flushdb before/after
- seed_user            — creates test user, returns user object
- seed_spot(user)      — creates surf spot with coordinates + region
- seed_profile(user, spot, conditions) — creates condition profile
- seed_forecast_redis(redis, spot, provider, model, points) — loads forecast data into Redis
```

**Key design decision**: Use `SAVEPOINT` (nested transactions) instead of full rollback for async tests. This allows service code to call `session.commit()` without breaking test isolation — the commit applies to the savepoint, not the outer transaction.

### File: `tests/integration/test_condition_profile_repo.py`

| Test | What it verifies |
|------|-----------------|
| `test_create_and_get_by_id` | Basic CRUD round-trip |
| `test_get_all_viewable_for_user_own_spots` | User sees profiles on their own spots |
| `test_get_all_viewable_for_user_crew_spots` | User sees profiles on crew member spots |
| `test_get_all_viewable_excludes_other_users` | User doesn't see unrelated profiles |
| `test_get_all_viewable_excludes_inactive` | `is_active=False` profiles filtered out |

### File: `tests/integration/test_condition_profile_service.py`

| Test | What it verifies |
|------|-----------------|
| `test_evaluate_all_viewable_with_matching_profile` | Seed DB + Redis → evaluate → matched=True |
| `test_evaluate_all_viewable_with_no_matching_profile` | Conditions outside forecast range → matched=False |
| `test_evaluate_with_missing_redis_data` | Forecast not in Redis → graceful None handling |
| `test_evaluate_multi_spot_concurrent` | Multiple spots evaluated concurrently via gather |

### File: `tests/integration/test_forecast_service.py`

| Test | What it verifies |
|------|-----------------|
| `test_get_forecasts_for_providers_pipeline` | Redis pipeline fetches correct subset |
| `test_get_forecasts_returns_empty_on_miss` | No Redis data → empty list (no crash) |

---

## What NOT to Test

| Skip | Why |
|------|-----|
| Route handler functions | Just glue: extract auth + call service/repo + wrap response |
| Repo simple CRUD (get_by_id, create, delete) | SQLAlchemy ORM — if the model is correct, CRUD works |
| Alembic migrations | Test by running `alembic upgrade head` in CI, not programmatically |
| FastAPI DI wiring | If deps are typed correctly, they compose correctly |
| Redis get/set operations | That's testing the Redis library, not your code |
| Pydantic serialization basics | Pydantic is well-tested; test YOUR validators, not theirs |

---

## GitHub Actions Setup

Two workflows:

### `test-unit.yml` — runs on every push

```yaml
name: Unit Tests
on: [push]

jobs:
  unit:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group test
      - run: uv run pytest -m unit --tb=short -q
```

### `test-integration.yml` — runs on PRs to main

```yaml
name: Integration Tests
on:
  pull_request:
    branches: [main]

jobs:
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose -f docker-compose.test.yml up -d --wait
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group test
        working-directory: backend
      - run: uv run pytest -m integration --tb=short -q
        working-directory: backend
      - run: docker compose -f docker-compose.test.yml down
```

---

## File Structure

```
tests/
├── conftest.py                              # Can be cleaned up / minimized
├── unit/
│   ├── __init__.py
│   ├── conftest.py                          # Factories: make_forecast_point, mock_profile, etc.
│   ├── test_condition_matching.py           # in_range, direction_in_range, entry_matches, evaluate_profile
│   ├── test_condition_schema.py             # Pydantic validation edge cases
│   ├── test_forecast_schema.py              # Redis serialization round-trips
│   └── test_workflow_transform.py           # Mapper + transform pure logic
└── integration/
    ├── __init__.py
    ├── conftest.py                          # DB + Redis fixtures, seed helpers
    ├── test_condition_profile_repo.py       # Complex query testing (viewable profiles JOIN)
    ├── test_condition_profile_service.py    # Full evaluation pipeline
    └── test_forecast_service.py             # Redis pipeline fetch
```

---

## Estimated Effort

| Phase | Tests | Time |
|-------|-------|------|
| Unit test setup (conftest + first file) | ~30 tests | 2-3 hours |
| Schema + serialization unit tests | ~12 tests | 1-2 hours |
| Workflow transform unit tests | ~5 tests | 1-2 hours |
| Integration conftest (fresh fixtures) | — | 1-2 hours |
| Integration tests | ~12 tests | 2-3 hours |
| GitHub Actions workflows | 2 files | 30 min |
| **Total** | **~60 tests** | **~8-12 hours** |

---

## Priority Order

1. `test_condition_matching.py` — highest risk logic, write first
2. `test_condition_schema.py` — catches bad user input before it hits the DB
3. `test_forecast_schema.py` — ensures Redis round-trips don't silently lose data
4. Integration `conftest.py` — foundation for all integration tests
5. `test_condition_profile_repo.py` — the viewable profiles query is the most complex SQL
6. `test_condition_profile_service.py` — full pipeline smoke test
7. `test_workflow_transform.py` — lower priority, workflows are already running in production
