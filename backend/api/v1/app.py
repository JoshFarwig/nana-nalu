import os
from typing import Union
from fastapi import FastAPI
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.logging import init_logging, get_logger


def create_app(config: str | None = None) -> FastAPI:
    """
    Factory function to create and configure the FastAPI application.
    This allows for better testing and modularity.
    """

    # Set up pydantic settings based on the environment
    # Throw an error if env is not of the 3 possible values
    config = config or os.getenv("FASTAPI_CONFIG", "dev")
    settings = get_settings(config)
    init_logging("INFO", settings.app_name)
    logger = get_logger(settings.app_name)
    logger.critical(
        f"Starting {settings.app_name} version {settings.app_version} in {config} mode"
    )
    logger.info("test")
    logger.debug("Debugging information here")
    logger.warning("This is a warning message")
    logger.error("An error occurred")

    # Set up conns (redis / database)

    # Set up routers / routes

    app = FastAPI()

    @app.get("/")
    def read_root():
        return {"Hello": "World"}

    return app
