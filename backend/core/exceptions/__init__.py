# TODO: After setting up spot forecast pipeline (retrieve via celery and set in redis)
# Start drafting out endpoint for surfspots and forecasts for surfspots, then add
# needed exception handles and/or custom classes here.
#

from .base import NanaNaluException, StartupError, DependencyError
from .handlers import (
    generic_exception_handler,
    validation_exception_handler,
    nana_nalu_exception_handler,
)


__all__ = [
    # Base Exceptions
    "NanaNaluException",
    "StartupError",
    "DependencyError",
    # Handlers
    "generic_exception_handler",
    "validation_exception_handler",
    "nana_nalu_exception_handler",
]
