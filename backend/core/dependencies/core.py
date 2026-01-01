import logging
from collections.abc import AsyncGenerator
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncDatabaseManager
from core.redis import AsyncRedisManager
from core.config import APISettings
from core.exceptions.base import DependencyError


logger = logging.getLogger(__name__)


# ======================================================
# Core Dependencies
# ======================================================


def get_settings(request: Request) -> APISettings:
    """
    Get application settings from app state.

    Args:
        request: FastAPI request object

    Returns:
        Application settings

    Raises:
        DependencyError: If settings not configured in app.state
    """
    settings: APISettings | None = getattr(request.app.state, "settings", None)
    if settings is None:
        raise DependencyError(
            "APISettings not available in app.state. "
            "Ensure application initialized properly."
        )
    return settings


def get_async_db_manager(request: Request) -> AsyncDatabaseManager:
    """
    Get database manager from app state.

    Args:
        request: FastAPI request object

    Returns:
        Database manager instance

    Raises:
        DependencyError: If database manager not configured in app.state
    """
    manager: AsyncDatabaseManager | None = getattr(
        request.app.state, "db_manager", None
    )
    if manager is None:
        raise DependencyError(
            "Database manager not available in app.state. "
            "Ensure application initialized properly."
        )
    return manager


def get_async_redis_manager(request: Request) -> AsyncRedisManager:
    """
    Get Redis manager from app state.

    Args:
        request: FastAPI request object

    Returns:
        Redis manager instance

    Raises:
        DependencyError: If Redis manager not configured in app.state
    """
    manager: AsyncRedisManager | None = getattr(
        request.app.state, "redis_manager", None
    )
    if manager is None:
        raise DependencyError(
            "Redis manager not available in app.state. "
            "Ensure application initialized properly."
        )
    return manager


# ======================================================
# Session Dependencies
# ======================================================


async def get_async_db_session(
    db_manager: AsyncDatabaseManager = Depends(get_async_db_manager),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session for endpoint injection.

    Uses 'async for' pattern because FastAPI's Depends() requires plain
    generators (functions with yield), not @asynccontextmanager decorated
    functions. FastAPI wraps plain generators internally to manage lifecycle,
    but cannot detect pre-decorated context managers before calling them.
    This may change in the future, but is the verified workaround as of
    now.

    See: https://github.com/fastapi/fastapi/discussions/8955
         https://github.com/fastapi/fastapi/pull/10353

    Args:
        db_manager: Database manager from app state

    Yields:
        AsyncSession: Database session with automatic lifecycle management
    """
    async for session in db_manager.get_explicit_commit_session():
        yield session
