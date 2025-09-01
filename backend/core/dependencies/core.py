from functools import lru_cache
import logging
import os
from fastapi import Depends
from typing import Annotated, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import BaseConfig, get_settings
from backend.core.database import DatabaseManager
from backend.core.redis import RedisManager
from backend.core.logging import init_logger


# Singleton dependencies with @lru_cache
@lru_cache()
def get_settings_dependency() -> BaseConfig:
    """Get singleton settings from environment."""

    # Read configuration from environment variable or default to 'dev'
    config = os.getenv("FASTAPI_CONFIG", "dev")
    return get_settings(config)


@lru_cache()
def get_logger_dependency(
    settings: BaseConfig = Depends(get_settings_dependency),
) -> logging.Logger:
    """Get singleton logger."""

    # Initialize logger with settings, this will be cached so
    # only initialized once per application run and should
    # return the same logger instance
    return init_logger(settings.log_level, settings.app_name)


@lru_cache()
def get_db_manager(
    settings: BaseConfig = Depends(get_settings_dependency),
) -> DatabaseManager:
    """Get singleton database manager."""
    return DatabaseManager(settings)  # Add logger if needed


@lru_cache()
def get_redis_manager(
    settings: BaseConfig = Depends(get_settings_dependency),
    logger: logging.Logger = Depends(get_logger_dependency),
) -> RedisManager:
    """Get singleton Redis manager."""
    return RedisManager(settings, logger)


# Session dependency - NOT cached, creates new session per request
async def get_db_session(
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> AsyncGenerator[AsyncSession, None]:
    """Get database session for use in endpoints."""
    async for session in db_manager.get_session():
        yield session
