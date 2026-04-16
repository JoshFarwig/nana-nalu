"""
Application configuration for different services.

Two service types: API (FastAPI) and Prefect (workflow worker). Environment-specific
settings (local, dev, prod) are handled via docker-compose env_file or exported
environment variables.

Usage:
    # In API service (api/v1/startup.py)
    from core.config import load_settings
    settings = load_settings("api")

    # In Prefect flows (workflows/...)
    settings = load_settings("prefect")
"""

from functools import lru_cache
from typing import Literal, Union, overload

from pydantic_settings import BaseSettings, SettingsConfigDict

from .configs import APIConfig, DatabaseConfig, HTTPConfig, RedisConfig


# ============================================================================
# Service-Specific Settings Classes
# ============================================================================


class APISettings(BaseSettings):
    """
    Configuration for API service.
    Requires: Database, Redis (Phase 2 removes), API config, HTTP client
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


class PrefectSettings(BaseSettings):
    """
    Configuration for Prefect worker service.

    Requires: Database (async), Redis (async — Phase 2 removes), HTTP client (async)
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


@overload
def load_settings(service_type: Literal["api"]) -> APISettings: ...


@overload
def load_settings(service_type: Literal["prefect"]) -> PrefectSettings: ...


@lru_cache
def load_settings(
    service_type: Literal["api", "prefect"] = "api",
) -> Union[APISettings, PrefectSettings]:
    """
    Load application settings based on service type.

    Args:
        service_type: Type of service ("api" or "prefect").

    Returns:
        Configuration object for the specified service type.
    """
    service_map = {
        "api": APISettings,
        "prefect": PrefectSettings,
    }

    ConfigClass = service_map[service_type]
    return ConfigClass()
