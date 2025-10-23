import logging
import socket
import os
import contextvars
from contextlib import contextmanager
from typing import Any

_log_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "log_context", default=None
)


class ContextFilter(logging.Filter):
    """Inject global and dynamic context into log records."""

    def __init__(self, name: str = ""):
        super().__init__(name)
        self.hostname = socket.gethostname()
        self.process_id = os.getpid()

    def filter(self, record: logging.LogRecord) -> bool:
        # global context
        record.hostname = self.hostname
        record.process_id = self.process_id

        # dynamic context (no mutable default)
        context = _log_context.get()
        if context is not None:
            for key, value in context.items():
                setattr(record, key, value)

        return True


@contextmanager
def log_context(**kwargs):
    """
    Add context to logs within this block.

    Example:
        with log_context(request_id = "123", user_id = "1")
            logger.info("Processing Request")
    """

    current = _log_context.get()
    if current is None:
        current = {}

    new_context = {**current, **kwargs}
    token = _log_context.set(new_context)

    try:
        yield
    finally:
        _log_context.reset(token)
