"""
Shared pytest fixtures for app.models tests.

Uses an in-memory SQLite database (via a shared StaticPool connection) so
tests are hermetic and fast, while still exercising the real SQLAlchemy
ORM models, constraints, and defaults defined in app.models.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base


@pytest.fixture()
def engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    # Enforce foreign key / constraint behavior consistently in SQLite.
    @event.listens_for(test_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Import models so metadata is fully populated before create_all.
    from app.models import recipe, session, audit_log, password_reset_token  # noqa: F401

    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture()
def db_session(engine) -> Session:
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def sample_owner_id() -> str:
    return str(uuid.uuid4())
