import os
from typing import Union
from fastapi import FastAPI
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.logging import init_logging, get_logger


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

    init_logging("DEBUG", settings.app_name)
    logger = get_logger(settings.app_name)
    # Set up pydantic settings based on the environment

    # Set up conns (redis / database)

    # Set up routers / routes

    app = FastAPI()

    @app.get("/")
    def read_root():
        return {"Hello": "World"}

    return app
