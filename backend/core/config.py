from pydantic_settings import BaseSettings, SettingsConfigDict

from .configs import APIConfig, DatabaseConfig, RedisConfig


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
    # celery: CeleryConfig
    db: DatabaseConfig
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


def get_settings(config: str) -> BaseConfig:
    """
    Reads config (typically the API_ENV os ENV) to pick which .env to load
    """

    mapping = {
        "local": LocalConfig,
        "dev": DevelopmentConfig,
        "prod": ProductionConfig,
    }

    cfg_cls = mapping.get(config)
    if not cfg_cls:
        raise RuntimeError(
            f"Unknown config type='{config}'"
            f"Available config types are {','.join(mapping.keys())}"
        )
    return cfg_cls()
