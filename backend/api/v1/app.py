import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from core.exceptions import (
    NanaNaluException,
    StartupError,
    generic_exception_handler,
    validation_exception_handler,
    nana_nalu_exception_handler,
)

from .startup import cleanup_app, init_app


logger = logging.getLogger(__name__)


# ======================================================
# App Lifespan
# ======================================================


def create_lifespan(config: str):
    """
    Create lifespan context manager with configuration.

    Args:
        config: Environment configuration ("dev", "prod", etc.)

    Returns:
        Async context manager for app lifecycle
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            # startup phase
            await init_app(app, config)
            logger.info(
                "Application started successfully",
                extra={
                    "config": config,
                    "api_name": app.state.settings.api.name,
                    "api_version": app.state.setings.api.version,
                },
            )

            yield

        except StartupError as e:
            logger.critical(
                "Application startup failed - cannot start server",
                extra={"error": str(e), "config": config},
            )
            raise  # re-raise to prevent app from starting
        finally:
            # shutdown phase (always runs, even if startup failed)
            await cleanup_app(app)

    return lifespan


# ======================================================
# App Factory
# ======================================================


def create_app(config: str | None = None) -> FastAPI:
    """
    Factory function to create and configure FastAPI application.

    Args:
        config: Environment configuration ("local", "dev", "prod").
                If None, uses API_ENV env var or defaults to "local".

    Returns:
        Configured FastAPI application instance
    """
    import os

    config = config or os.getenv("API_ENV", "local")
    api_name = os.getenv("API_NAME", "nānā-nalu-api")
    api_version = os.getenv("API_VERSION", "0.1.0")

    app = FastAPI(
        title=api_name,
        version=api_version,
        description="Surf forecasting and spot management API",
        lifespan=create_lifespan(config),
    )

    # exception handlers
    app.add_exception_handler(NanaNaluException, nana_nalu_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)

    # ======================================================
    # Routes
    # ======================================================

    @app.get("/", tags=["root"])
    def read_root():
        """Root endpoint - basic API information."""
        return {
            "message": "nānā-nalu surf forecasting API",
            "api_version": app.version,
            "docs": "/docs",
        }

    @app.get("/health", tags=["health"])
    async def health_check():
        """
        Basic health check endpoint.

        Returns 200 if the application is running. For more detailed
        infrastructure health checks, use /health/detailed endpoint.
        """
        return {"status": "healthy", "service": "nānā-nalu-api"}

    # TODO: Include routers
    # from backend.api.v1.routes import users, spots, forecasts
    # app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    # app.include_router(spots.router, prefix="/api/v1/spots", tags=["spots"])
    # app.include_router(forecasts.router, prefix="/api/v1/forecasts", tags=["forecasts"])

    return app
