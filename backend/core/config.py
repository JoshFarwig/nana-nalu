from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

from utils import Environment, EnvironmentMapper
from .configs import APIConfig, CeleryConfig, DatabaseConfig, HTTPConfig, RedisConfig


class BaseConfig(BaseSettings):
    """
    Nana Nalu's Configuration, includes all primary configurations for
    the python backend.
    """

    # nested configurations will only load
    # such that their var names match
    # the named prefix and the nested delimiter i.e.
    # API__ADMIN_PASSWORD for api.admin_password
    # of APIConfig object.

    api: APIConfig
    celery: CeleryConfig

    db: DatabaseConfig
    http: HTTPConfig
    redis: RedisConfig


class LocalConfig(BaseConfig):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
    )


class DevelopmentConfig(BaseConfig):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
        # secrets_dir="/run/secrets",  # NOTE: docker container secrets
        # NOTE: pydantic-settings will default delimiter for secrets as the env_nested_delimiter
        # once pydantic-settings v2.12 is out, can use secrets via SettingsConfigDict
        # secrets_nested_delimiter="__"
    )


class ProductionConfig(BaseConfig):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
        # secrets_dir="/run/secrets",  # NOTE: docker container secrets
        # NOTE: pydantic-settings will default delimiter for secrets as the env_nested_delimiter
        # once pydantic-settings v2.12 is out, can use secrets via SettingsConfigDict
        # secrets_nested_delimiter="__"
    )


@lru_cache()
def get_settings(env: Environment | str | None = None) -> BaseConfig:
    """
    Get application settings based on environment.

    Args:
        env: Environment to load. If None, reads from ENV variable.
             Can be Environment enum or string that will be normalized.

    Returns:
        Configuration object for the specified environment
    """
    # normalize environment using EnvironmentMapper
    if isinstance(env, str):
        environment = EnvironmentMapper.normalize(env)
    elif env is None:
        environment = EnvironmentMapper.normalize()
    else:
        environment = env

    mapping = {
        Environment.LOCAL: LocalConfig,
        Environment.DEV: DevelopmentConfig,
        Environment.PROD: ProductionConfig,
    }

    cfg_cls = mapping[environment]
    return cfg_cls()
