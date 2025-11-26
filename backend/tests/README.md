# Testing Guide for nānā-nalu Backend

## Quick Start

### 1. Start Test Services
```bash
# From project root
docker compose -f docker-compose.test.yml up -d

# Verify services are healthy
docker compose -f docker-compose.test.yml ps
```

### 2. Run Integration Tests
```bash
# From backend directory
cd backend

# Run all integration tests
pytest -m integration -v

# Run specific test
pytest tests/integration/test_nwps_pipeline.py -v

# Run with detailed output
pytest -m integration -v -s
```

### 3. Stop Test Services
```bash
docker compose -f docker-compose.test.yml down

# Clean up volumes if needed
docker compose -f docker-compose.test.yml down -v
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures (DB, Redis, HTTP managers)
├── integration/             # Integration tests (require Docker)
│   └── test_nwps_pipeline.py
└── unit/                    # Unit tests (fast, no dependencies)
    └── (future unit tests)
```

## Fixtures Available

### Sync Fixtures (for Celery/Worker tests)
- `sync_db_session` - SQLAlchemy sync session with transaction rollback
- `sync_db_manager` - SyncDatabaseManager for Celery-style operations
- `sync_redis_client` - Redis sync client with auto-flush
- `sync_redis_manager` - SyncRedisManager for Celery operations
- `sample_maui_spots` - Pre-seeded Maui surf spots (Ho'okipa, Hamoa)

### Async Fixtures (for API tests)
- `async_db_session` - SQLAlchemy async session with transaction rollback
- `async_db_manager` - AsyncDatabaseManager for FastAPI-style operations
- `async_redis_client` - Redis async client with auto-flush
- `async_redis_manager` - AsyncRedisManager for FastAPI operations
- `async_sample_maui_spots` - Async version of sample_maui_spots

### Shared Fixtures
- `http_manager` - SyncHTTPManager for GRIB downloads
- `test_db_config` - Test database configuration
- `test_redis_config` - Test Redis configuration

## Writing New Tests

### Integration Test Example
```python
import pytest
from sqlalchemy.orm import Session

@pytest.mark.integration
def test_my_feature(sync_db_session: Session, sync_redis_client, sample_maui_spots):
    # Your test code here
    pass
```

### Async API Test Example
```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.integration
async def test_my_api_endpoint(async_db_session: AsyncSession, async_redis_client):
    # Your async test code here
    pass
```

## Troubleshooting

### Tests hang or timeout
- Verify Docker services are running: `docker compose -f docker-compose.test.yml ps`
- Check service health: Both test-db and test-redis should show "healthy"
- View logs: `docker compose -f docker-compose.test.yml logs`

### Connection refused errors
- Test services use different ports to avoid conflicts:
  - PostgreSQL: `5433` (dev uses 5432)
  - Redis: `6380` (dev uses 6379)
- Ensure these ports are available

### GRIB download failures
- NOMADS server may be down or slow
- Check if the analysis time matches available data
- Try the mock test variant for offline development

### Database schema errors
- Tables are created from models in `conftest.py`
- If models changed, restart test services to recreate schema
- Use `docker compose -f docker-compose.test.yml down -v` to fully reset

## CI/CD Integration

To run tests in GitHub Actions or similar:

```yaml
- name: Start test services
  run: docker compose -f docker-compose.test.yml up -d

- name: Wait for services
  run: |
    timeout 60 bash -c 'until docker compose -f docker-compose.test.yml ps | grep -q healthy; do sleep 2; done'

- name: Run tests
  run: |
    cd backend
    pytest -m integration -v

- name: Cleanup
  run: docker compose -f docker-compose.test.yml down
```
