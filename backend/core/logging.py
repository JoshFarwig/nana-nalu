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
    name: str,
    level: str = "INFO",
) -> logging.Logger:
    # Simplified format without logger_type
    fmt = (
        "%(levelname)s %(asctime)s - "
        "%(filename)s:%(lineno)d %(funcName)s(): %(message)s"
    )
    formatter = ColorFormatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False

    return logger


# default logger
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
