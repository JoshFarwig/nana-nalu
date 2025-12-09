"""
Application configuration for different services.

Each service (API, Worker, Scheduler) has its own settings class that defines
only the configuration it needs. Environment-specific settings (local, dev, prod)
are handled via docker-compose env_file or exported environment variables.

Usage:
    # In API service (api/v1/startup.py or main.py)
    from core.config import load_settings
    settings = load_settings("api")

    # In Worker service (workers/worker_app.py)
    settings = load_settings("worker")

    # In Scheduler services (workers/beat_app.py, workers/flower_app.py)
    settings = load_settings("scheduler")
"""

from functools import lru_cache
from typing import Literal, Union, overload

from pydantic_settings import BaseSettings, SettingsConfigDict

from .configs import APIConfig, CeleryConfig, DatabaseConfig, HTTPConfig, RedisConfig


# ============================================================================
# Service-Specific Settings Classes
# ============================================================================
# Each class defines ONLY the configuration fields that service needs.
# No inheritance, no dynamic class creation, just explicit field definitions.


class APISettings(BaseSettings):
    """
    Configuration for API service.
    Requires: Database, Redis, API-specific settings, HTTP client
    """

    model_config = SettingsConfigDict(
        frozen=True,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
        extra="ignore",
    )

    db: DatabaseConfig
    redis: RedisConfig
    api: APIConfig
    http: HTTPConfig = HTTPConfig()


class WorkerSettings(BaseSettings):
    """
    Configuration for Celery worker service.
    Requires: Database (for task execution), Redis, Celery, HTTP client
    """

    model_config = SettingsConfigDict(
        frozen=True,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
        extra="ignore",
    )

    db: DatabaseConfig
    redis: RedisConfig
    celery: CeleryConfig = CeleryConfig()
    http: HTTPConfig = HTTPConfig()


class SchedulerSettings(BaseSettings):
    """
    Configuration for Celery beat and Flower services.
    Requires: Only Redis and Celery (no database, no API config)
    """

    model_config = SettingsConfigDict(
        frozen=True,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
        extra="ignore",
    )

    redis: RedisConfig
    celery: CeleryConfig = CeleryConfig()


# ============================================================================
# Settings Factory with Type-Safe Overloads
# ============================================================================
# The overloads tell type checkers exactly what type is returned for each
# service_type literal, enabling full autocomplete and type checking.


@overload
def load_settings(service_type: Literal["api"] = "api") -> APISettings: ...


@overload
def load_settings(service_type: Literal["worker"] = "worker") -> WorkerSettings: ...


@overload
def load_settings(service_type: Literal["scheduler"] = "scheduler") -> SchedulerSettings: ...


@lru_cache
def load_settings(
    service_type: Literal["api", "worker", "scheduler"] = "api",
) -> Union[APISettings, WorkerSettings, SchedulerSettings]:
    """
    Load application settings based on service type.

    Environment-specific configuration (local vs dev vs prod) is handled by:
    - Docker: --env-file flag in docker-compose command
    - Local: Exported environment variables or .env.local file

    Args:
        service_type: Type of service ("api", "worker", or "scheduler").
                     Determines which configuration fields are required.

    Returns:
        Configuration object for the specified service type with full type hints.

    Examples:
        >>> # API service
        >>> settings = load_settings("api")
        >>> settings.db.host  # Type checker knows this exists
        >>> settings.api.admin_username  # Autocomplete works!

        >>> # Scheduler service (beat/flower)
        >>> settings = load_settings("scheduler")
        >>> settings.redis.host  # Type checker knows this exists
        >>> settings.db  # ❌ Type checker error: SchedulerSettings has no 'db'

    Notes:
        - The function is cached with @lru_cache, so calling it multiple times
          with the same service_type returns the same instance.
        - Settings are loaded from environment variables with the __ delimiter
          (e.g., DB__HOST, REDIS__PASSWORD, API__ADMIN_USERNAME).
        - Missing required environment variables will raise ValidationError at
          import/startup time (fail-fast behavior).
    """
    service_map = {
        "api": APISettings,
        "worker": WorkerSettings,
        "scheduler": SchedulerSettings,
    }

    ConfigClass = service_map[service_type]
    return ConfigClass()
