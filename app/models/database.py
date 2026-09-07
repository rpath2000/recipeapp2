"""Database engine, declarative Base, ORM models, and session factory.

This module is the single source of database configuration for the
application. It builds its engine from the DATABASE_URL environment
variable exclusively (defaulting to a local SQLite database when it is
unset), and never reads DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD.
"""
import os
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)

SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, future=True
)

Base = declarative_base()


def _utcnow() -> datetime:
    """Return the current UTC time (naive) for storage in TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Recipe(Base):
    """Persistent record of a recipe.

    Columns map to DR-001 through DR-005:
      - id: auto-incrementing integer primary key.
      - name: VARCHAR(120) NOT NULL.
      - ingredients: VARCHAR(4000) NOT NULL.
      - created_at: TIMESTAMP (UTC), set once on insert.
      - updated_at: TIMESTAMP (UTC), set on insert and on every update.
    """

    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    ingredients = Column(String(4000), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session.

    Commits the transaction on normal exit and rolls back on exception,
    always closing the session afterward.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
