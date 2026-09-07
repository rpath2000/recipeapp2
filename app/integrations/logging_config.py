"""
Structured (JSON) logging configuration honoring NFR-013.

Provides:
- configure_logging(): sets up a JSON-formatted root logger using the
  LOG_LEVEL from get_settings().
- request_context / bind_request_context / get_request_context: a
  contextvars-based mechanism so log records emitted anywhere during a
  request automatically carry request-scoped context (request id, path,
  method, etc.) without threading it through every call site.

No I/O or side effects happen at import time beyond defining classes and
contextvars; configure_logging() must be called explicitly (e.g. from the
application startup hook) to attach handlers.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Mapping

from app.integrations.config import get_settings

_REQUEST_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "request_context", default={}
)

_RESERVED_LOG_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "taskName",
}


def bind_request_context(**fields: Any) -> contextvars.Token:
    """Merge fields into the current request context. Returns a reset token."""
    current = dict(_REQUEST_CONTEXT.get())
    current.update(fields)
    return _REQUEST_CONTEXT.set(current)


def reset_request_context(token: contextvars.Token) -> None:
    """Restore request context to its state before the matching bind call."""
    _REQUEST_CONTEXT.reset(token)


def get_request_context() -> dict[str, Any]:
    """Return a copy of the current request context."""
    return dict(_REQUEST_CONTEXT.get())


def clear_request_context() -> None:
    """Reset request context to empty. Intended for tests."""
    _REQUEST_CONTEXT.set({})


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON with request context."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        context = get_request_context()
        if context:
            payload["request_context"] = context

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_ATTRS and not key.startswith("_")
        }
        if extras:
            payload["extra"] = extras

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(handler_stream: Any = None) -> None:
    """Configure the root logger with a JSON formatter and LOG_LEVEL.

    Idempotent: safe to call multiple times (e.g. across module reloads
    in tests) - it replaces any previously attached handlers rather than
    stacking duplicates.
    """
    settings = get_settings()

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)

    stream = handler_stream if handler_stream is not None else sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger. Does not configure handlers."""
    return logging.getLogger(name)
