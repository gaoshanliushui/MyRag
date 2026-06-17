"""
Logging Configuration

Structured logging with Rich console output for development
and JSON logging for production.
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

from app.config import settings

# Context variables for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")


class StructuredFormatter(logging.Formatter):
    """JSON-style structured formatter for production."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "tenant_id": tenant_id_var.get(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {"name", "msg", "args", "created", "filename", "funcName",
                           "levelname", "levelno", "lineno", "module", "msecs",
                           "pathname", "process", "processName", "relativeCreated",
                           "stack_info", "exc_info", "exc_text", "message", "asctime"}:
                log_data[key] = value

        # Simple JSON-like output (no external dependency)
        return str(log_data)


def setup_logging() -> None:
    """Configure logging based on environment."""
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Remove existing handlers
    root_logger.handlers.clear()

    if settings.DEBUG:
        # Rich console handler for development
        console = Console(stderr=True)
        handler = RichHandler(
            console=console,
            show_time=True,
            show_path=True,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        # Structured JSON handler for production
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(StructuredFormatter(datefmt="%Y-%m-%d %H:%M:%S"))

    root_logger.addHandler(handler)

    # Set levels for noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("elasticsearch").setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("pymilvus").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


class RequestLogContext:
    """Context manager for request logging context."""

    def __init__(self, request_id: str, tenant_id: str = ""):
        self.request_id = request_id
        self.tenant_id = tenant_id
        self._request_id_token = None
        self._tenant_id_token = None

    def __enter__(self) -> "RequestLogContext":
        self._request_id_token = request_id_var.set(self.request_id)
        self._tenant_id_token = tenant_id_var.set(self.tenant_id)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._request_id_token:
            request_id_var.reset(self._request_id_token)
        if self._tenant_id_token:
            tenant_id_var.reset(self._tenant_id_token)


# Initialize logging on import
setup_logging()

# Module-level logger
logger = get_logger("myrag")