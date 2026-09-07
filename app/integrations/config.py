"""
Configuration management for the application.

Loads DATABASE_URL and LOG_LEVEL from the environment, exposes a cached
settings singleton via get_settings(), and exposes get_engine() which
lazily builds (and caches) the SQLAlchemy engine used by the whole app.

No network / database I/O happens at import time: building an Engine
object with create_engine() does not open a connection, it only
configures the connection factory. The actual connection is established
lazily on first use (or explicitly verified via check_connection()),
which callers should invoke from an application startup hook rather
than at import time.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_VALID_SCHEMES = {
    "postgresql",
    "postgresql+psycopg2",
    "postgresql+asyncpg",
    "mysql",
    "mysql+pymysql",
    "sqlite",
}

_DEFAULT_DATABASE_URL = "sqlite:///./recipeapp2book.db"
_DEFAULT_LOG_LEVEL = "INFO"
_EXPECTED_DB_NAME = "recipeapp2book"

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class ConfigurationError(Exception):
    """Raised when application configuration is missing or malformed."""


@dataclass(frozen=True)
class Settings:
    """Immutable configuration singleton for the application."""

    database_url: str
    log_level: str


def _validate_database_url(database_url: str | None) -> str:
    """Validate DATABASE_URL, failing fast with a clear message on error."""
    if database_url is None or database_url.strip() == "":
        raise ConfigurationError(
            "Configuration error: DATABASE_URL environment variable is "
            "missing. Set DATABASE_URL to a valid SQLAlchemy database URL "
            "pointing at the 'recipeapp2book' database "
            "(e.g. postgresql://user:pass@host:5432/recipeapp2book)."
        )

    database_url = database_url.strip()

    try:
        parsed = urlparse(database_url)
    except Exception as exc:  # pragma: no cover - urlparse rarely raises
        raise ConfigurationError(
            f"Configuration error: DATABASE_URL is malformed: {exc}"
        ) from exc

    if not parsed.scheme:
        raise ConfigurationError(
            "Configuration error: DATABASE_URL is malformed - missing "
            f"scheme (e.g. 'postgresql://'). Got: {database_url!r}"
        )

    if parsed.scheme not in _VALID_SCHEMES:
        raise ConfigurationError(
            "Configuration error: DATABASE_URL uses an unsupported scheme "
            f"{parsed.scheme!r}. Supported schemes: {sorted(_VALID_SCHEMES)}."
        )

    # sqlite URLs (e.g. sqlite:///./file.db) do not carry a network path
    # component the same way, so only enforce the database-name check for
    # network-backed engines.
    if parsed.scheme != "sqlite":
        if not parsed.path or parsed.path.strip("/") == "":
            raise ConfigurationError(
                "Configuration error: DATABASE_URL is malformed - missing "
                f"database name. Got: {database_url!r}"
            )

        db_name = parsed.path.strip("/")
        if db_name != _EXPECTED_DB_NAME:
            logger.warning(
                "DATABASE_URL points at database %r, expected %r. "
                "Continuing with configured value.",
                db_name,
                _EXPECTED_DB_NAME,
            )

    return database_url


def _validate_log_level(log_level: str | None) -> str:
    """Validate LOG_LEVEL, defaulting and normalizing as needed."""
    if log_level is None or log_level.strip() == "":
        return _DEFAULT_LOG_LEVEL

    normalized = log_level.strip().upper()
    if normalized not in _VALID_LOG_LEVELS:
        raise ConfigurationError(
            f"Configuration error: LOG_LEVEL {log_level!r} is invalid. "
            f"Valid values are: {sorted(_VALID_LOG_LEVELS)}."
        )
    return normalized


def _build_settings() -> Settings:
    """Read and validate configuration from the environment."""
    raw_database_url = os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)
    raw_log_level = os.environ.get("LOG_LEVEL", _DEFAULT_LOG_LEVEL)

    database_url = _validate_database_url(raw_database_url)
    log_level = _validate_log_level(raw_log_level)

    return Settings(database_url=database_url, log_level=log_level)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide configuration singleton.

    Fails fast (raises ConfigurationError) if DATABASE_URL is missing or
    malformed. Cached so repeated calls do not re-parse the environment.
    """
    return _build_settings()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine.

    Building the engine does not open a connection - SQLAlchemy connects
    lazily on first use. Cached so the whole application shares one
    connection pool.
    """
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
        future=True,
    )
    return engine


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide sessionmaker bound to get_engine()."""
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def check_connection() -> None:
    """Verify database connectivity. Call from an application startup hook.

    Raises ConfigurationError with a clear message if the connection
    cannot be established. This performs real I/O and must never be
    called at import time.
    """
    from sqlalchemy import text

    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise ConfigurationError(
            f"Configuration error: unable to connect to the database "
            f"using the configured DATABASE_URL: {exc}"
        ) from exc


def reset_config_cache() -> None:
    """Clear cached settings/engine/sessionmaker. Intended for tests only."""
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
