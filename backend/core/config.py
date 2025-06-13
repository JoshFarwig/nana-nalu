# app/config.py
import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    # general application settings
    app_name: str = "nānā-nalu-backend"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    debug: bool = False  # whether to run in debug mode

    # db settings
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # note: no default env_file here, subclasses override it
    # and all vars will be loaded from that file.
    # can add a default value .env file for base configurations if needed
    model_config = SettingsConfigDict(env_file=None)


class DevelopmentConfig(BaseConfig):
    # general application settings
    log_level: str = "DEBUG"
    debug: bool = True

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
    # general application settings
    log_level: str = "DEBUG"
    debug: bool = False

    # db settings
    # TODO: use a test database URL or mock the database? or sqlite for unit tests?
    model_config = SettingsConfigDict(
        env_file=".env.test",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings(config: str) -> BaseConfig:
    """
    Reads FASTAPI_CONFIG to pick which .env to load.
    CACHE so that multiple calls share one instance.
    """
    # note: this may cause issues if the environment variable is in hot-reloading (caching issue) scenarios?
    # not sure need to test
    mapping = {
        "dev": DevelopmentConfig,
        "prod": ProductionConfig,
        "test": TestConfig,
    }
    cfg_cls = mapping.get(config)
    if not cfg_cls:
        raise RuntimeError(f"Unknown FASTAPI_CONFIG='{config}'")
    return cfg_cls()
