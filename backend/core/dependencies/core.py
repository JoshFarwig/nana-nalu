import logging
from fastapi import Depends, Request
from typing import Annotated

from backend.core.config import BaseConfig
from backend.core.database import DatabaseManager


def get_settings_dependency(request: Request) -> BaseConfig:
    """Get settings from app state."""
    return request.app.state.settings


def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app state."""
    return request.app.state.db_manager


def get_logger_dependency(request: Request) -> logging.Logger:
    """Get logger from app state."""
    return request.app.state.logger


async def get_db_session(
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
):
    """Get database session for use in endpoints."""
    async for session in db_manager.get_session():
        yield session
