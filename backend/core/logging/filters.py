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


class PrefectContextFilter(logging.Filter):
    """
    Inject Prefect flow/task context into log records for console/JSON output.

    Uses Prefect's runtime context to automatically add display-friendly fields:
    - flow_name: Current flow name (if in a flow)
    - flow_run_short_id: Short flow run ID (first 8 chars)
    - task_name: Current task name (if in a task)
    - task_run_short_id: Short task run ID (first 8 chars)

    NOTE: Uses *_short_id to avoid colliding with Prefect's internal
    flow_run_id / task_run_id fields that the APILogHandler needs as full UUIDs.

    Also supports dynamic context via log_context() context manager.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Try to get Prefect context (lazy import to avoid circular deps)
        try:
            from prefect.context import get_run_context
            from prefect.context import TaskRunContext, FlowRunContext

            ctx = get_run_context()

            if isinstance(ctx, FlowRunContext):
                record.flow_name = ctx.flow.name
            elif isinstance(ctx, TaskRunContext):
                record.task_name = ctx.task.name
                # Task runs also have parent flow context
        except Exception:
            # Not in a Prefect context, that's fine
            pass

        # dynamic context via log_context() still works
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
