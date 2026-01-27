"""
Application configuration for different services.

Each service (API, Worker, Scheduler, Prefect) has its own settings class that defines
only the configuration it needs. Environment-specific settings (local, dev, prod)
are handled via docker-compose env_file or exported environment variables.

Usage:
    # In API service (api/v1/startup.py or main.py)
    from core.config import load_settings
    settings = load_settings("api")

    # In Celery Worker service (workers/worker_app.py)
    settings = load_settings("worker")

    # In Celery Scheduler services (workers/beat_app.py, workers/flower_app.py)
    settings = load_settings("scheduler")

    # In Prefect flows (prefect/nomads/orchestration.py)
    settings = load_settings("prefect")
"""

from functools import lru_cache
from typing import Literal, Union, overload

from pydantic_settings import BaseSettings, SettingsConfigDict

from .configs import APIConfig, CeleryConfig, DatabaseConfig, HTTPConfig, RedisConfig


# ============================================================================
# Service-Specific Settings Classes
# ============================================================================
# each class defines ONLY the configuration fields that service needs.


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


class PrefectSettings(BaseSettings):
    """
    Configuration for Prefect worker service.

    Requires: Database (async), Redis (async), HTTP client (async)
    Does NOT require: Celery config, API config

    Similar to WorkerSettings but without Celery dependency.
    Used for the Celery → Prefect migration.
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
    http: HTTPConfig = HTTPConfig()


# ============================================================================
# Settings Factory with Type-Safe Overloads
# ============================================================================
# The overloads tell type checkers exactly what type is returned for each
# service_type literal, enabling full autocomplete and type checking.


@overload
def load_settings(service_type: Literal["api"]) -> APISettings: ...


@overload
def load_settings(service_type: Literal["worker"]) -> WorkerSettings: ...


@overload
def load_settings(service_type: Literal["scheduler"]) -> SchedulerSettings: ...


@overload
def load_settings(service_type: Literal["prefect"]) -> PrefectSettings: ...


@lru_cache
def load_settings(
    service_type: Literal["api", "worker", "scheduler", "prefect"] = "api",
) -> Union[APISettings, WorkerSettings, SchedulerSettings, PrefectSettings]:
    """
    Load application settings based on service type.

    Environment-specific configuration (local vs dev vs prod) is handled by:
    - Docker: --env-file flag in docker-compose command
    - Local: Exported environment variables or .env.local file

    Args:
        service_type: Type of service ("api", "worker", "scheduler", or "prefect").
                     Determines which configuration fields are required.

    Returns:
        Configuration object for the specified service type with full type hints.

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
        "prefect": PrefectSettings,
    }

    ConfigClass = service_map[service_type]
    return ConfigClass()
