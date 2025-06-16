import os
from contextlib import asynccontextmanager
from typing import Union
from fastapi import FastAPI
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.logging import init_fastapi_logger
from backend.core.database import DatabaseManager
from backend.core.dependencies.core import (
    get_settings_dependency,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    config = os.getenv("FASTAPI_CONFIG", "dev")
    settings = get_settings(config)

    # Set up logger for fastapi
    logger = init_fastapi_logger(settings.log_level, settings.app_name)

    # Initialize database via db manager
    db_manager = DatabaseManager(settings)

    # Store thing in app.state
    app.state.settings = settings
    app.state.db_manager = db_manager
    app.state.logger = logger

    logger.info(f"Application {settings.app_name} started")

    yield

    # Shutdown for app
    await db_manager.close()
    logger.info("Application shutdown complete")


def create_app(config: str | None = None) -> FastAPI:
    """
    Factory function to create and configure the FastAPI application.
    This function initializes logging, sets up configuration settings,
    initializes database connections, and sets up routes.
    Args:
        config (str | None): The configuration environment to use.
                             If None, it will read from the FASTAPI_CONFIG
                             environment variable. Valid values are "dev",
                             "prod", or "test".
    """
    # Set up configuration and settings, pass settings to services via DI if needed.
    config = config or os.getenv("FASTAPI_CONFIG", "dev")
    settings = get_settings(config)

    # Create FastAPI app with lifespan context manager
    app = FastAPI(
        title=settings.app_name, version=settings.app_version, lifespan=lifespan
    )

    # Initialize logging
    logger = init_fastapi_logger(level=settings.log_level, logger_type="FastAPI")

    # Set the app state with settings and logger
    app.state.settings = settings
    app.state.logger = logger
    app.state.db_manager = (
        None  # Placeholder for database manager, to be initialized later
    )

    @app.get("/")
    def read_root():
        logger.info("Root endpoint called")
        return {"Hello": "World"}

    # Set up application routes
    from backend.api.v1.routes import users

    app.include_router(users.router, prefix="/users", tags=["users"])

    return app
