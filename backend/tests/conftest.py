"""
Pytest fixtures for integration tests.

To run integration tests:
1. Start test services: docker compose -f docker-compose.test.yml up -d
2. Run tests: pytest -m integration
3. Stop services: docker compose -f docker-compose.test.yml down
"""

from typing import AsyncGenerator, Generator
import pytest
import redis
import redis.asyncio as aioredis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from models.base_model import Base
from core.configs.database_config import DatabaseConfig
from core.configs.redis_config import RedisConfig
from core.database import SyncDatabaseManager, AsyncDatabaseManager
from core.redis import SyncRedisManager, AsyncRedisManager
from pydantic import SecretStr


# =========================
# TEST CONFIGURATION
# =========================


@pytest.fixture(scope="session")
def test_db_config() -> DatabaseConfig:
    """Test database configuration matching docker-compose.test.yml"""
    return DatabaseConfig(
        host="localhost",
        port="5433",  # Test DB port
        username="test_user",
        password=SecretStr("test_password"),
        name="test_nana_nalu",
    )


@pytest.fixture(scope="session")
def test_redis_config() -> RedisConfig:
    """Test Redis configuration matching docker-compose.test.yml"""
    return RedisConfig(
        host="localhost",
        port=6380,  # Test Redis port
        password=SecretStr("test_redis_password"),
    )


# =========================
# SYNC DATABASE FIXTURES (for Celery/worker tests)
# =========================


@pytest.fixture(scope="session")
def sync_db_engine(test_db_config: DatabaseConfig):
    """Create test database engine (session-scoped for performance)"""
    engine = create_engine(test_db_config.get_sy────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────nc_url())

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Teardown: drop all tables
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="session")
def sync_session_factory(sync_db_engine):
    """Create a sessionmaker bound to the test engine"""
    return sessionmaker(bind=sync_db_engine)


@pytest.fixture(scope="function")
def sync_db_session(sync_db_engine) -> Generator[Session, None, None]:
    """
    Create a clean database session for each test (sync version).

    Uses transaction rollback pattern for test isolation:
    - Each test runs in a transaction
    - Transaction is rolled back after test completes
    - Ensures tests don't interfere with each other
    """
    connection = sync_db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def sync_db_manager(test_db_config: DatabaseConfig, sync_session_factory):
    """
    Database manager for Celery-style sync operations.

    Uses the test sessionmaker for proper session management.
    """
    manager = SyncDatabaseManager(test_db_config)
    # Replace with test session factory
    manager._session_factory = sync_session_factory

    yield manager


# =========================
# ASYNC DATABASE FIXTURES (for API tests)
# =========================


@pytest.fixture(scope="session")
async def async_db_engine(test_db_config: DatabaseConfig):
    """Create async test database engine (session-scoped for performance)"""
    engine = create_async_engine(test_db_config.get_async_url())

    # Note: Table creation must be done with sync engine (see sync_db_engine)
    # This fixture assumes tables already exist from sync_db_engine

    yield engine

    await engine.dispose()


@pytest.fixture(scope="session")
def async_session_factory(async_db_engine):
    """Create an async sessionmaker bound to the test engine"""
    return async_sessionmaker(async_db_engine, expire_on_commit=False)


@pytest.fixture(scope="function")
async def async_db_session(async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a clean async database session for each test.

    Uses transaction rollback pattern for test isolation.
    """
    async with async_db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)

        yield session

        await session.close()
        await transaction.rollback()


@pytest.fixture(scope="function")
async def async_db_manager(test_db_config: DatabaseConfig, async_session_factory):
    """
    Database manager for FastAPI-style async operations.

    Uses the test sessionmaker for proper session management.
    """
    manager = AsyncDatabaseManager(test_db_config)
    # Replace with test session factory
    manager._session_factory = async_session_factory

    yield manager


# =========================
# SYNC REDIS FIXTURES (for Celery/worker tests)
# =========================


@pytest.fixture(scope="function")
def sync_redis_client(test_redis_config: RedisConfig):
    """
    Redis client for sync tests (function-scoped for isolation).

    Flushes the cache database before and after each test.
    """
    client = redis.from_url(
        test_redis_config.get_cache_url(),
        encoding="utf-8",
        decode_responses=True,
    )

    # Clear Redis before test
    client.flushdb()

    yield client

    # Clear Redis after test
    client.flushdb()
    client.close()


@pytest.fixture(scope="function")
def sync_redis_manager(test_redis_config: RedisConfig, sync_redis_client: redis.Redis):
    """
    Redis manager for Celery-style sync operations.

    Injects the test client to ensure test isolation.
    """
    cache_url = test_redis_config.get_cache_url()
    manager = SyncRedisManager(test_redis_config, cache_url)
    # Override the client to use our test client
    manager._client = sync_redis_client

    yield manager

    # No cleanup needed - handled by sync_redis_client fixture


# =========================
# ASYNC REDIS FIXTURES (for API tests)
# =========================


@pytest.fixture(scope="function")
async def async_redis_client(test_redis_config: RedisConfig):
    """
    Async Redis client for API tests (function-scoped for isolation).

    Flushes the cache database before and after each test.
    """
    client = await aioredis.from_url(
        test_redis_config.get_cache_url(),
        encoding="utf-8",
        decode_responses=True,
    )

    # Clear Redis before test
    await client.flushdb()

    yield client

    # Clear Redis after test
    await client.flushdb()
    await client.aclose()


@pytest.fixture(scope="function")
async def async_redis_manager(
    test_redis_config: RedisConfig, async_redis_client: aioredis.Redis
):
    """
    Async Redis manager for FastAPI-style async operations.

    Injects the test client to ensure test isolation.
    """
    cache_url = test_redis_config.get_cache_url()
    manager = AsyncRedisManager(test_redis_config, cache_url)
    # Override the client to use our test client
    manager._client = async_redis_client

    yield manager

    # No cleanup needed - handled by async_redis_client fixture


# =========================
# HTTP FIXTURES
# =========================


@pytest.fixture(scope="session")
def http_manager():
    """HTTP manager for downloading GRIB files in tests"""
    from core.http import SyncHTTPManager
    from core.configs.http_config import HTTPConfig

    config = HTTPConfig()
    manager = SyncHTTPManager(config, retry=False)

    yield manager

    manager.close()


# =========================
# HELPER FIXTURES
# =========================


@pytest.fixture
def sample_maui_spots(sync_db_session: Session):
    """
    Create sample Maui surf spots for testing NWPS pipeline.

    Uses actual spots from seed data: Ho'okipa and Hamoa Beach.
    These are within the NWPS Maui grid configuration.
    """
    from models.surf_spot_model import SurfSpot
    from models.user_model import User
    from geoalchemy2 import WKTElement

    # Create test user (required FK for surf spots)
    user = User(
        username="test_user",
        email="test@example.com",
        password="hashed_pw",
    )
    sync_db_session.add(user)
    sync_db_session.flush()  # Get user.id

    # Use actual Maui spots from seed data
    spots = [
        SurfSpot(
            name="Ho'okipa (Point)",
            description="The iconic NSB grom-grounds (Point, Middles, Pavillions)",
            location=WKTElement("POINT(-156.3596 20.9342)", srid=4326),
            is_active=True,
            created_by_id=user.id,
        ),
        SurfSpot(
            name="Hamoa beach",
            description="Hana's day dream point and beach break (and sandbar one bay over)",
            location=WKTElement("POINT(-155.9865 20.7184)", srid=4326),
            is_active=True,
            created_by_id=user.id,
        ),
    ]

    for spot in spots:
        sync_db_session.add(spot)

    sync_db_session.commit()

    # Refresh to get IDs
    for spot in spots:
        sync_db_session.refresh(spot)

    return spots
