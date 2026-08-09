"""
Database health check and connection retry logic.

This module NEVER defines its own database configuration. It relies on
the shared session/engine wiring provided by app.models.database, which
is the single source of truth for DATABASE_URL and connection pooling.

Exposes:
- check_db_health(db: Session) -> bool: quick liveness probe (<100ms
  when reachable), used by health endpoints and other clients.
- with_db_retry: retry decorator/helper for transient DB errors, useful
  for callers that need resilient DB access (e.g. background jobs).
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

logger = logging.getLogger("app.integrations.db_health")

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 0.1
HEALTH_CHECK_TIMEOUT_SECONDS = 0.1  # 100ms budget for the probe itself

T = TypeVar("T")


def check_db_health(db: Session) -> bool:
    """Execute a trivial query to verify database connectivity.

    Returns True when the database responds successfully, False
    otherwise. Never raises: all exceptions are caught, logged with
    structured context, and translated into a False result so callers
    (e.g. health endpoints) can respond gracefully.
    """
    start = time.monotonic()
    try:
        db.execute(text("SELECT 1"))
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Database health check succeeded",
            extra={
                "operation": "check_db_health",
                "resource": "database",
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )
        return True
    except (OperationalError, DBAPIError) as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.error(
            "Database health check failed",
            extra={
                "operation": "check_db_health",
                "resource": "database",
                "error": str(exc),
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )
        return False
    except Exception as exc:  # defensive: never let health check raise
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.error(
            "Database health check failed with unexpected error",
            extra={
                "operation": "check_db_health",
                "resource": "database",
                "error": str(exc),
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )
        return False


def with_db_retry(func: Callable[[], T], operation_name: str = "db_operation") -> T:
    """Execute `func` with retry-on-transient-error semantics.

    Retries up to MAX_RETRIES times with exponential backoff when a
    SQLAlchemy OperationalError (typically transient connectivity
    issues) is raised. Re-raises the last exception if all attempts
    fail, preserving the original error context for callers.
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return func()
        except OperationalError as exc:
            last_exc = exc
            logger.warning(
                "Database operation failed, retrying",
                extra={
                    "operation": operation_name,
                    "resource": "database",
                    "error": str(exc),
                    "attempt": attempt,
                    "max_attempts": MAX_RETRIES,
                },
            )
            if attempt == MAX_RETRIES:
                break
            time.sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

    logger.error(
        "Database operation failed after retries",
        extra={
            "operation": operation_name,
            "resource": "database",
            "error": str(last_exc),
            "attempts": MAX_RETRIES,
        },
    )
    assert last_exc is not None
    raise last_exc
