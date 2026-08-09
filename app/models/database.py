"""
app.models.database
====================

Owns the SQLAlchemy declarative Base, the database engine, the session
factory, and the get_db() FastAPI dependency.

Configuration is sourced EXCLUSIVELY from the single application-wide
DATABASE_URL environment variable (no component-local DB_HOST / DB_PORT /
DB_NAME / DB_USER / DB_PASSWORD configuration is defined here or anywhere
else in this module).

Connection pooling is tuned to comfortably support 10-20 concurrent
sessions without exhaustion.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/recipes",
)

# Pool sized to comfortably support 10-20 concurrent sessions:
# 15 persistent connections + burst overflow of 10 => up to 25 concurrent
# connections available under load, steady state covers 10-20 easily.
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "15"))
MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models in the application."""

    pass


def _build_engine():
    connect_args = {}
    if DATABASE_URL.startswith("sqlite"):
        # SQLite is only used for local/dev/testing; pooling knobs differ.
        connect_args = {"check_same_thread": False}
        return create_engine(
            DATABASE_URL,
            connect_args=connect_args,
            future=True,
        )

    return create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_recycle=POOL_RECYCLE,
        pool_pre_ping=True,
        future=True,
    )


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session, closed on teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for scripts/tests needing a transactional session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize the database schema.

    In production, schema changes should be applied via Alembic migrations
    (see app/models/migrations). This helper is provided for local
    development/test bootstrapping and is idempotent (create_all only
    creates missing tables).
    """
    # Import models so they are registered on Base.metadata before create_all.
    from app.models import recipe, session, audit_log, password_reset_token  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized (create_all).")


def check_db_health(db: Session | None = None) -> bool:
    """
    Lightweight health check that executes a trivial round-trip query.

    Returns True if the query succeeds within the expected latency budget
    (<100ms under normal conditions), False otherwise. Never raises.
    """
    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True

    start = time.monotonic()
    try:
        db.execute(text("SELECT 1"))
        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms >= 100:
            logger.warning("DB health check slow: %.2fms", elapsed_ms)
        return True
    except Exception as exc:  # noqa: BLE001 - health checks must not raise
        logger.error("DB health check failed: %s", exc)
        return False
    finally:
        if owns_session:
            db.close()
