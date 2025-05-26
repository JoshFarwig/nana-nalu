# app/config.py
import os
from functools import lru_cache
from pydantic import BaseSettings
from pydantic_settings import SettingsConfigDict


class BaseConfig(BaseSettings):
    # common settings:
    app_name: str
    database_url: str

    # note: no default env_file here, subclasses override it
    model_config = SettingsConfigDict(env_file=None)


class DevelopmentConfig(BaseConfig):
    model_config = SettingsConfigDict(
        env_file=".env.dev",
        env_file_encoding="utf-8",
    )


class ProductionConfig(BaseConfig):
    model_config = SettingsConfigDict(
        env_file=".env.prod",
        env_file_encoding="utf-8",
    )


class TestConfig(BaseConfig):
    model_config = SettingsConfigDict(
        env_file=".env.test",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> BaseConfig:
    """
    Reads FASTAPI_CONFIG to pick which .env to load.
    CACHE so that multiple calls share one instance.
    """
    mapping = {
        "dev": DevelopmentConfig,
        "prod": ProductionConfig,
        "test": TestConfig,
    }
    cfg_name = os.getenv("FASTAPI_CONFIG", "dev")
    cfg_cls = mapping.get(cfg_name)
    if not cfg_cls:
        raise RuntimeError(f"Unknown FASTAPI_CONFIG='{cfg_name}'")
    return cfg_cls()
