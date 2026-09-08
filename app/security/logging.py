"""
Security-relevant structured logging for the application.

This module implements the shared `setup_logging` seam consumed by the
application entrypoint (app.main). It configures a structured, stdout-only
logging pipeline and exposes a small set of helper functions used by other
components (e.g. app.services.recipe) to record security-relevant events
such as validation failures and unhandled exceptions.

SEC-001 NOTICE
--------------
No authentication or authorization is implemented anywhere in this
application. All HTTP routes are publicly accessible. This is a deliberate,
documented scope decision (SEC-001) and not an oversight. Any future work
that adds authentication/authorization must update this notice and the
project's requirements traceability matrix.

Design notes
------------
- Logging is structured as single-line JSON so it can be ingested by log
  aggregation tools without additional parsing logic.
- Nothing sensitive (passwords, secrets, tokens, personal data) is ever
  logged. Recipe content is user-supplied but non-sensitive; even so, we
  truncate long values defensively before logging them.
- `setup_logging()` is idempotent: calling it multiple times (e.g. once from
  the entrypoint and once from a test) will not duplicate log handlers.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Name of the logger used for all security-relevant events in this module.
SECURITY_LOGGER_NAME = "app.security"

# Name of the logger used for HTTP request/response access logging.
ACCESS_LOGGER_NAME = "app.security.access"

# Maximum length of any single user-supplied value included in a log record.
_MAX_LOGGED_VALUE_LENGTH = 200


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Fields:
        timestamp: ISO-8601 UTC timestamp.
        level: standard logging level name.
        logger: name of the logger that emitted the record.
        message: the rendered log message.
        Any extra structured fields attached via `extra=` are merged in.
    """

    _RESERVED_ATTRS = {
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
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in self._RESERVED_ATTRS or key.startswith("_"):
                continue
            if key == "message":
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging() -> None:
    """Configure structured, stdout-only logging for the whole application.

    This is the seam exported for the entrypoint: `app.security.logging`.
    It attaches a single StreamHandler (stdout) with a JSON formatter to the
    root logger, so that every module's `logging.getLogger(__name__)` calls
    are captured uniformly. Safe to call more than once.
    """
    root_logger = logging.getLogger()

    # Remove any handlers previously installed by this function to keep the
    # operation idempotent (avoids duplicate log lines in tests / reload).
    for handler in list(root_logger.handlers):
        if getattr(handler, "_security_module_handler", False):
            root_logger.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler._security_module_handler = True  # type: ignore[attr-defined]

    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Document SEC-001 loudly at startup so operators see it in the logs.
    security_logger = logging.getLogger(SECURITY_LOGGER_NAME)
    security_logger.info(
        "security_startup_notice",
        extra={
            "event": "security_startup_notice",
            "detail": (
                "SEC-001: No authentication or authorization is implemented. "
                "All routes are publicly accessible by design."
            ),
        },
    )


def _truncate(value: str) -> str:
    """Truncate a user-supplied string defensively before logging it."""
    if value is None:
        return ""
    if len(value) > _MAX_LOGGED_VALUE_LENGTH:
        return value[:_MAX_LOGGED_VALUE_LENGTH] + "...<truncated>"
    return value


def log_validation_failure(
    *,
    field: str,
    reason: str,
    value: str | None = None,
) -> None:
    """Log a security-relevant validation failure.

    Called by services (e.g. RecipeService) whenever a ValidationError is
    raised, so that potential SQL injection / XSS probing attempts against
    input fields are visible in the structured logs.
    """
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    logger.warning(
        "validation_failure",
        extra={
            "event": "validation_failure",
            "field": field,
            "reason": reason,
            "value": _truncate(value) if value is not None else None,
        },
    )


def log_unhandled_exception(
    *,
    context: str,
    exc: BaseException,
) -> None:
    """Log an unhandled exception with security-relevant context."""
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    logger.error(
        "unhandled_exception",
        extra={
            "event": "unhandled_exception",
            "context": context,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        },
        exc_info=exc,
    )


def log_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float | None = None,
) -> None:
    """Log an HTTP request with method, path and status for observability.

    Intended to be called from request middleware in the entrypoint (or any
    component that wires HTTP middleware) to provide structured, correlated
    access logs. No authentication context is logged because none exists
    (SEC-001): all routes are public.
    """
    logger = logging.getLogger(ACCESS_LOGGER_NAME)
    logger.info(
        "http_request",
        extra={
            "event": "http_request",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "authenticated": False,
        },
    )
