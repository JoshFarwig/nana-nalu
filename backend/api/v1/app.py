import os
from contextlib import asynccontextmanager
from typing import Union
from fastapi import FastAPI
from pydantic import BaseModel

from core.config import get_settings
from core.logging import init_logger

from core.database import DatabaseManager
from core.redis import RedisManager


def create_lifespan(config_override: str | None = None):
    """Create lifespan function with optional config override."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Use override if provided, otherwise fall back to env var, then default
        config = config_override or os.getenv("FASTAPI_CONFIG", "dev")
        settings = get_settings(config)

        # Initialize core services
        logger = init_logger(
            settings.app_name,
            settings.log_level,
        )
        db_manager = DatabaseManager(settings)
        redis_manager = RedisManager(settings, logger)

        # Store in app state for singletone pattern
        app.state.settings = settings
        app.state.logger = logger
        app.state.db_manager = db_manager
        app.state.redis_manager = redis_manager

        logger.info(f"Application {settings.app_name} started with config: {config}")

        yield

        # Cleanup
        await db_manager.close()
        await redis_manager.close()
        logger.info("Application shutdown complete")

    return lifespan


def create_app(config: str | None = None) -> FastAPI:
    """
    Factory function to create and configure the FastAPI application.

    Args:
        config: Configuration environment ("dev", "prod", "test").
                If None, uses FASTAPI_CONFIG env var or defaults to "dev".
    """

    app = FastAPI(
        title="nānā nalu API",
        version="0.1.0",
        lifespan=create_lifespan(config),  # Pass config to lifespan
    )

    @app.get("/")
    def read_root():
        return {"message": "nānā nalu surf forecasting API"}

    # TODO: Include routers
    # from backend.api.v1.routes import users, spots, forecasts

    # app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    # app.include_router(spots.router, prefix="/api/v1/spots", tags=["spots"])
    # app.include_router(forecasts.router, prefix="/api/v1/forecasts", tags=["forecasts"])

    return app
