from enum import Enum
import os


class Environment(str, Enum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"
    TEST = "test"


def get_env() -> Environment:
    val = os.getenv("ENV")
    if val is None:
        raise ValueError(
            "ENV not set. Valid: " + ", ".join(e.value for e in Environment)
        )
    try:
        return Environment(val.lower())
    except ValueError:
        raise ValueError(
            f"Unknown ENV: {val}. Valid: {[e.value for e in Environment]}"
        )
