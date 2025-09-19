import os
from contextlib import asynccontextmanager
from typing import Union
from fastapi import FastAPI
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.dependencies.core import (
    get_db_manager,
    get_logger_dependency,
    get_settings_dependency,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    settings = get_settings_dependency()
    db_manager = get_db_manager()
    logger = get_logger_dependency()

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
    settings = get_settings_dependency()

    # Create FastAPI app with lifespan context manager
    app = FastAPI(
        title=settings.app_name, version=settings.app_version, lifespan=lifespan
    )

    @app.get("/")
    def read_root():
        app.state.logger.info("Root endpoint called")
        return {"Hello": "World"}

    # Set up application routes
    from backend.api.v1.routes import users

    app.include_router(users.router, prefix="/users", tags=["users"])

    return app
