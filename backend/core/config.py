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

    # sqlalchemy settings
    engine_echo: bool = False  # whether to log SQL queries
    engine_pool_size: int = 5  # number of connections in the pool
    engine_max_overflow: int = (
        10  # number of connections allowed to exceed the pool size
    )
    engine_pool_timeout: int = (
        30  # seconds to wait before giving up on getting a connection from the pool
    )
    session_expire_on_commit: bool = False  # whether to expire session after commit

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

    # sqlalchemy settings
    engine_echo: bool = True  # log SQL queries in development

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
