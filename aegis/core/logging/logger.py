"""
Aegis — Structured JSON Logging

Provides structured JSON logging with correlation / request ID tracking.
Ensures uniform logging across the FastAPI application, Celery workers, and background jobs.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Context variable to hold the active request / correlation ID across async execution
correlation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def get_correlation_id() -> str | None:
    """Retrieve the current correlation / request ID from context."""
    return correlation_id_ctx.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the current correlation / request ID in context."""
    correlation_id_ctx.set(correlation_id)


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Include file/line metadata for debugging
        if record.levelno >= logging.WARNING:
            log_payload["source"] = f"{record.pathname}:{record.lineno}"

        # Include exception trace if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Include any extra structured context passed via extra={}
        if hasattr(record, "extra_context") and isinstance(record.extra_context, dict):
            log_payload.update(record.extra_context)

        return json.dumps(log_payload)


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configures root logger with JSON formatting and returns the main application logger."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not any(isinstance(h.formatter, JSONFormatter) for h in root_logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        root_logger.handlers = [handler]

    return logging.getLogger("aegis")
