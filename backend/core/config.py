from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

from utils import Environment, EnvironmentMapper
from .configs import APIConfig, CeleryConfig, DatabaseConfig, HTTPConfig, RedisConfig


class BaseConfig(BaseSettings):
    """
    Nana Nalu's Configuration, includes all primary configurations for
    the python backend.
    """

    # NOTE: nested configurations will only load
    # such that their var names match
    # the named prefix and the nested delimiter i.e.
    # DB__PASSWORD for db.password
    # of DatabaseConfig object.

    db: DatabaseConfig
    redis: RedisConfig

    # NOTE: nested configurations with sensible defaults
    # that do not require any env fields should instantiate
    # with a default config object, env fields will override

    # TODO: since celery does not need reference to api,
    # setting default to None, I could make an explicit difference
    # between api vs worker config but idk or have defaults for all api values.
    # but if I have defaults for the api values an instantiate them on celery,
    # wouldn't be the same if I don't pass the API envs / secrets to the celery
    # instances. so idk. this may be the best approach to juse default it to none
    api: APIConfig | None = None
    celery: CeleryConfig = CeleryConfig()
    http: HTTPConfig = HTTPConfig()


class LocalConfig(BaseConfig):
    model_config = SettingsConfigDict(
        frozen=True,
        env_file=".env.local",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
        extra="ignore",
    )


class DevelopmentConfig(BaseConfig):
    model_config = SettingsConfigDict(
        frozen=True,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
        extra="ignore",
        # secrets_dir="/run/secrets",  # NOTE: docker container secrets
        # NOTE: pydantic-settings will default delimiter for secrets as the env_nested_delimiter
        # once pydantic-settings v2.12 is out, can use secrets via SettingsConfigDict
        # secrets_nested_delimiter="__"
    )


class ProductionConfig(BaseConfig):
    model_config = SettingsConfigDict(
        frozen=True,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_nested_max_split=1,
        extra="ignore",
        # secrets_dir="/run/secrets",  # NOTE: docker container secrets
        # NOTE: pydantic-settings will default delimiter for secrets as the env_nested_delimiter
        # once pydantic-settings v2.12 is out, can use secrets via SettingsConfigDict
        # secrets_nested_delimiter="__"
    )


ENVIRONMENT_CONFIG_REGISTRY: dict[Environment, type[BaseConfig]] = {
    Environment.LOCAL: LocalConfig,
    Environment.DEV: DevelopmentConfig,
    Environment.PROD: ProductionConfig,
}


@lru_cache
def load_settings(env: Environment | str | None = None) -> BaseConfig:
    """
    Load application settings based on environment.

    Args:
        env: Environment to load. If None, reads from ENV environment variable.
             Can be Environment enum or string that will be normalized.

    Returns:
        Configuration object for the specified environment
    """
    # normalize environment using EnvironmentMapper
    if isinstance(env, Environment):
        environment = env
    else:
        environment = EnvironmentMapper.normalize(env)

    cfg_cls = ENVIRONMENT_CONFIG_REGISTRY[environment]
    return cfg_cls()  # type: ignore[arg-type] api, db and celery are instantiated from ENVS.
