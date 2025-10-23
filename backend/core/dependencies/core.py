import logging
from collections.abc import AsyncGenerator
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core import AsyncDatabaseManager, AsyncRedisManager, BaseConfig

from core.exceptions import DependencyError


logger = logging.getLogger(__name__)


# ======================================================
# Core Dependencies
# ======================================================


def get_settings(request: Request) -> BaseConfig:
    """
    Get application settings from app state.

    Args:
        request: FastAPI request object

    Returns:
        Application settings

    Raises:
        DependencyError: If settings not configured in app.state
    """
    settings: BaseConfig | None = getattr(request.app.state, "settings", None)
    if settings is None:
        raise DependencyError(
            "Settings not available in app.state. "
            "Ensure application initialized properly."
        )
    return settings


def get_db_manager(request: Request) -> AsyncDatabaseManager:
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


def get_redis_manager(request: Request) -> AsyncRedisManager:
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


async def get_db_session(
    db_manager: AsyncDatabaseManager = Depends(get_db_manager),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session for endpoint injection.

    Uses async for to iterate over the db_manager's session generator, ensuring
    proper session lifecycle management is delegated to the db_manager's get_session
    (creation and cleanup). The yielded session is injected into endpoint functions
    via FastAPI's dependency system.

    Args:
        db_manager: Database manager from app state

    Yields:
        AsyncSession: Database session with automatic lifecycle management
    """
    async for session in db_manager.get_session():
        yield session
