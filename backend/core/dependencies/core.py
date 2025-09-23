from functools import lru_cache
import logging
import os
from fastapi import Depends, Request
from typing import Annotated, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import BaseConfig
from core.database import DatabaseManager
from core.redis import RedisManager
from core.logging import init_logger


# Simple singleton DI extractors from app.state
def get_settings(request: Request) -> BaseConfig:
    """Get settings from app state."""
    return request.app.state.settings


def get_logger(request: Request) -> logging.Logger:
    """Get logger from app state."""
    return request.app.state.logger


def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app state."""
    return request.app.state.db_manager


def get_redis_manager(request: Request) -> RedisManager:
    """Get Redis manager from app state."""
    return request.app.state.redis_manager


# Session dependency for endpoints
async def get_db_session(
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> AsyncGenerator[AsyncSession, None]:
    """Get database session for use in endpoints."""
    async for session in db_manager.get_session():
        yield session
