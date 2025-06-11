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
    # and all vars will be loaded from that file.
    # can add a default value .env file for base configurations if needed
    model_config = SettingsConfigDict(env_file=None)


class DevelopmentConfig(BaseConfig):
    model_config = SettingsConfigDict(
        _env_file=".env.dev",
        env_file_encoding="utf-8",
    )

    # general application settings
    app_name: str = "My FastAPI App (Development)"
    app_version: str = "0.1.0"
    debug: bool = True

    # redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379

    # postgres db settings
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "nn-db"
    db_user: str = "nn-base-user"
    db_password: str = "nn-base-pass"


class ProductionConfig(BaseConfig):
    model_config = SettingsConfigDict(
        _env_file=".env.prod",
        env_file_encoding="utf-8",
    )


class TestConfig(BaseConfig):
    model_config = SettingsConfigDict(
        _env_file=".env.test",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> BaseConfig:
    """
    Reads FASTAPI_CONFIG to pick which .env to load.
    CACHE so that multiple calls share one instance.
    """
    # note: this may cause issues if the environment variable is in hot-reloading scenarios? not sure need to test
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
