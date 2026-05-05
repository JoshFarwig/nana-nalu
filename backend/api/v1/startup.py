import logging
from fastapi import FastAPI

from core.database import AsyncDatabaseManager
from core.http import AsyncHTTPManager
from core.config import APISettings
from core.logging.config import configure_logging
from utils.env import get_env
from core.exceptions.base import StartupError

logger = logging.getLogger(__name__)


# ======================================================
# App Lifecycle
# ======================================================


async def init_app(app: FastAPI) -> None:
    """
    Initialize FastAPI application with all required resources.

    Steps:
        1. Configure logging
        2. Load settings
        3. Initialize infrastructure managers
        4. Perform health checks

    Raises:
        StartupError: If any initialization step fails
    """
    env = get_env()

    # configure logging first
    configure_logging(env)
    logger.info("Starting application initialization", extra={"config": env.value})

    # load settings
    from core.config import load_settings

    try:
        settings = load_settings("api")
        app.state.settings = settings
        logger.info(
            "Settings loaded successfully",
            extra={
                "config": env.value,
                "api_name": settings.api.name,
                "api_version": settings.api.version,
            },
        )
    except Exception as e:
        logger.exception("Failed to load settings", extra={"config": env.value})
        raise StartupError(f"Settings initialization failed: {e}") from e

    # initialize infrastructure managers
    try:
        await _init_infrastructure(app, settings)
        logger.info("Infrastructure managers initialized", extra={"config": env.value})
    except Exception as e:
        logger.exception(
            "Failed to initialize infrastructure", extra={"config": env.value}
        )
        await _cleanup_infrastructure(app)
        raise StartupError(f"Infrastructure initialization failed: {e}") from e

    # perform health checks
    try:
        await _health_check_infrastructure(app)
        logger.info(
            "All infrastructure health checks passed", extra={"config": env.value}
        )
    except Exception as e:
        logger.exception(
            "Infrastructure health check failed", extra={"config": env.value}
        )
        await _cleanup_infrastructure(app)
        raise StartupError(f"Health check failed: {e}") from e

    logger.info(
        "Application initialization complete",
        extra={"config": env.value, "api_name": settings.api.name},
    )


async def cleanup_app(app: FastAPI) -> None:
    """
    Clean up application resources on shutdown.

    Args:
        app: FastAPI application instance
    """
    logger.info("Starting application shutdown")
    await _cleanup_infrastructure(app)
    logger.info("Application shutdown complete")


# ======================================================
# Infrastructure Management
# ======================================================


async def _init_infrastructure(app: FastAPI, settings: APISettings) -> None:
    """
    Initialize and attach infrastructure managers to app state.

    Args:
        app: FastAPI application instance
        settings: Application settings
    """
    logger.debug("Creating infrastructure managers")

    # initialize database manager
    db_manager = AsyncDatabaseManager(settings.db)
    app.state.db_manager = db_manager
    logger.debug(
        "Database manager created", extra={"pool_size": settings.db.async_pool_size}
    )

    # initialize HTTP manager for external API calls
    http_manager = AsyncHTTPManager(settings.http)
    app.state.http_manager = http_manager
    logger.debug(
        "HTTP manager created",
        extra={
            "timeout": settings.http.timeout,
            "max_attempts": settings.http.max_attempts,
        },
    )


async def _health_check_infrastructure(app: FastAPI) -> None:
    """
    Verify all infrastructure managers are healthy.

    Args:
        app: FastAPI application instance

    Raises:
        RuntimeError: If any health check fails
    """
    logger.debug("Starting infrastructure health checks")

    # check database
    db_healthy = await app.state.db_manager.health_check()
    if not db_healthy:
        logger.error("Database health check failed")
        raise RuntimeError("Database health check failed")
    logger.info("Database health check passed")


async def _cleanup_infrastructure(app: FastAPI) -> None:
    """
    Clean up infrastructure managers, safely handling partial initialization.

    This function is designed to be idempotent and handle cases where
    managers may not be fully initialized.

    Args:
        app: FastAPI application instance
    """
    logger.debug("Starting infrastructure cleanup")

    # clean up database manager
    db_manager: AsyncDatabaseManager | None = getattr(app.state, "db_manager", None)
    if db_manager:
        try:
            await db_manager.close()
            logger.info("Database manager closed successfully")
        except Exception as e:
            logger.error(
                "Error closing database manager", extra={"error": str(e)}, exc_info=True
            )
        finally:
            app.state.db_manager = None

    # clean up HTTP manager
    http_manager: AsyncHTTPManager | None = getattr(app.state, "http_manager", None)
    if http_manager:
        try:
            await http_manager.close()
            logger.info("HTTP manager closed successfully")
        except Exception as e:
            logger.error(
                "Error closing HTTP manager", extra={"error": str(e)}, exc_info=True
            )
        finally:
            app.state.http_manager = None

    logger.debug("Infrastructure cleanup complete")
