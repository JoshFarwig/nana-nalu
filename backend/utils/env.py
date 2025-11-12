from enum import Enum
import os


class Environment(str, Enum):
    """Application environment Types"""

    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"
    TEST = "test"


class EnvironmentMapper:
    """Env Mapper"""

    # Normaliation Map
    _ENV_MAP = {
        "local": Environment.LOCAL,
        "dev": Environment.DEV,
        "development": Environment.DEV,
        "prod": Environment.PROD,
        "production": Environment.PROD,
        "test": Environment.TEST,
    }

    @classmethod
    def normalize(cls, env: str | None = None) -> Environment:
        """Normalize enviroment type and map to Enum"""

        if env is None:
            env = os.getenv("ENV")
            if env is None:
                raise ValueError(
                    "ENV variable is not set, and cannot normalize. "
                    "Please set it to one of " + ", ".join(cls._ENV_MAP.keys())
                )

        normalized_env = cls._ENV_MAP.get(env.lower())

        if normalized_env is None:
            raise ValueError(
                f"Unknown env value: {env.lower()}. "
                "Please pass a valid value: " + ", ".join(cls._ENV_MAP.keys())
            )

        return normalized_env

    @classmethod
    def is_local(cls, env: str | None = None) -> bool:
        """Helper method to check if enviroment is local"""
        return cls.normalize(env) == Environment.LOCAL

    @classmethod
    def is_dev(cls, env: str | None = None) -> bool:
        """Helper method to check if enviroment is dev"""
        return cls.normalize(env) == Environment.DEV

    @classmethod
    def is_prod(cls, env: str | None = None) -> bool:
        """Helper method to check if enviroment is prod"""
        return cls.normalize(env) == Environment.PROD

    @classmethod
    def is_test(cls, env: str | None = None) -> bool:
        """Helper method to check if enviroment is test"""
        return cls.normalize(env) == Environment.TEST


# Convenience Methods


def get_env() -> Environment | None:
    return EnvironmentMapper.normalize()


def is_local() -> bool:
    return EnvironmentMapper.is_local()


def is_dev() -> bool:
    return EnvironmentMapper.is_dev()


def is_prod() -> bool:
    return EnvironmentMapper.is_prod()


def is_test() -> bool:
    return EnvironmentMapper.is_test()
