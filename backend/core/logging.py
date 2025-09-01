import time
import logging

# ANSI color codes for log levels
LOG_COLORS = {
    "DEBUG": "\033[46m",  # White text on Cyan background
    "INFO": "\033[42m",  # White text on Green background
    "WARNING": "\033[43m",  # White text on Yellow background
    "ERROR": "\033[41m",  # White text on Red background
    "CRITICAL": "\033[1m\033[45m",  # Bold white text on Magenta background
}

RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.converter = time.gmtime  # Use UTC time for log timestamps

    def format(self, record):
        color = LOG_COLORS.get(record.levelname, "")
        record.levelname = f"{color} {record.levelname} {RESET}"
        return super().format(record)


def init_logger(
    level: str = "INFO", logger_type: str | None = "default"
) -> logging.Logger:

    fmt = (
        "%(levelname)s %(asctime)s - %(logger_type)s "
        "%(filename)s:%(lineno)d %(funcName)s(): %(message)s"
    )
    formatter = ColorFormatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger(logger_type)
    logger.handlers.clear()  # could this cause race condition? if lru locks itself should be fine.
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False

    return logger


# default logger
def get_logger(name: str | None = "default") -> logging.Logger:
    return logging.getLogger(name)
