"""Database engine, session factory, and get_db dependency.

This module builds the SQLAlchemy engine from app.db_url.DATABASE_URL
(the single source of truth for the connection string), and re-exports
the shared Base and ORM models for `from app.models.database import ...`
and `from app.models import ...` usage.

No connection is opened at import time: create_engine only registers the
driver and connection args, it does not connect. Importing this module
must succeed even with no database reachable, since alembic, pytest and
build-time import checks all import the app without a live database.
"""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db_url import DATABASE_URL
from app.models.base import Base
from app.models.recipe import Recipe

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session, closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "Recipe", "engine", "SessionLocal", "get_db"]
