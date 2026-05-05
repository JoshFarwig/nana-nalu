import yaml
import logging
import logging.config
from pathlib import Path

from utils.env import Environment, get_env


def _get_logging_config_path(env: Environment | None = None) -> Path:
    """Get Path to logging config files"""
    if env is None:
        env = get_env()

    if env == Environment.LOCAL:
        filename = "logging.dev.yaml"  # default to development configuration if running locally
    else:
        filename = f"logging.{env.value}.yaml"

    return Path(__file__).parent / filename


def configure_logging(env: Environment | None = None) -> None:
    """Configure logging via yaml files, else fallback"""

    config_filepath = _get_logging_config_path(env)

    if config_filepath.exists():
        with open(config_filepath, "r") as f:
            config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)

        resolved_env = env or get_env()
        logger = logging.getLogger(__name__)
        logger.info(
            f"Successfully set up logger with configuation {config_filepath} for enviroment {resolved_env.value}"
        )
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning(
            f"Logging configuration not found {config_filepath}. "
            "Defaulting to python's default logging configuation..."
        )


def get_logger(name: str | None = None) -> logging.Logger:
    """Convenience method to get logger"""

    return logging.getLogger(name)
