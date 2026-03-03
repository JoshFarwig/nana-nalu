import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.exceptions.base import NanaNaluException, StartupError
from utils.region import get_enabled_regions
from core.exceptions.handlers import (
    generic_exception_handler,
    validation_exception_handler,
    http_exception_handler,
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
                    "environment": config,
                    "api_name": app.state.settings.api.name,
                    "api_version": app.state.settings.api.version,
                    "regions": [r.value for r in get_enabled_regions()],
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
                If None, reads from ENV environment variable.
                String will be normalized using EnvironmentMapper.

    Returns:
        Configured FastAPI application instance
    """
    import os
    from utils.env import EnvironmentMapper

    # normalize config if provided as string, otherwise use ENV variable
    if config:
        env = EnvironmentMapper.normalize(config)
        config = env.value
    else:
        env = EnvironmentMapper.normalize()
        config = env.value

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
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)

    # ======================================================
    # Root Routes
    # ======================================================

    @app.get("/", tags=["root"])
    def read_root():
        """Root endpoint - basic API information."""
        return {
            "message": "nānā-nalu surf forecasting API",
            "api_version": app.version,
        }

    @app.get("/health", tags=["health"])
    async def health_check():
        """
        Basic health check endpoint.

        Returns 200 if the application is running. For more detailed
        infrastructure health checks, use /health/detailed endpoint.
        """
        return {"status": "healthy", "service": "nānā-nalu-api"}

    # ======================================================
    # API v1 Router Setup
    # ======================================================

    from fastapi import APIRouter
    from api.v1.routes import auth, users, surf_spots

    api_v1_router = APIRouter(prefix="/api/v1")
    api_v1_router.include_router(auth.router)
    api_v1_router.include_router(users.router)
    api_v1_router.include_router(surf_spots.router)

    # mount the entire v1 API under /api/v1
    app.include_router(api_v1_router)

    return app
