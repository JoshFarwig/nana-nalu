import logging

# get base LogRecord attributes
_RESERVED_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {
    # attributes that could be added by Formatter
    "message",
    "asctime",
    "exc_text",
    "stack_info",
    "taskName",
}


class ColoredConsoleFormatter(logging.Formatter):
    """Console formatter with colors for stdout logs"""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        if record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}{self.RESET}"
            )

        formatted = super().format(record)

        extra_fields = self._get_extra_fields(record)
        if extra_fields:
            extra_str = ", ".join(f"{k}={v}" for k, v in extra_fields.items())
            # inject extra fields into stdout log
            formatted = f"{formatted}\nextra: [{self.BOLD}{extra_str}{self.RESET}]"

        return formatted

    def _get_extra_fields(self, record):
        """Extract extra fields from the log record."""
        extra = {}
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                extra[key] = value
        return extra
