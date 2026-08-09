"""
Tests for the connection pool / session factory behavior and the health
check utility.
"""

from __future__ import annotations

import threading
import time
import uuid

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.models.database import Base, check_db_health
from app.models.recipe import Recipe


def _build_pooled_engine():
    test_engine = create_engine(
        "sqlite:///file:pooltest?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=15,
        max_overflow=10,
        future=True,
    )

    @event.listens_for(test_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return test_engine


def test_connection_pool_handles_concurrent_session_requests():
    engine = _build_pooled_engine()
    from app.models import recipe, session, audit_log, password_reset_token  # noqa: F401

    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    errors: list[Exception] = []
    results: list[bool] = []
    lock = threading.Lock()

    def worker():
        try:
            db = TestSessionLocal()
            try:
                recipe_obj = Recipe(
                    name=f"Concurrent Recipe {uuid.uuid4()}",
                    description="desc",
                    ingredients="ingredients",
                    instructions="instructions",
                    category="dinner",
                    owner_id=str(uuid.uuid4()),
                )
                db.add(recipe_obj)
                db.commit()
                with lock:
                    results.append(True)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(18)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Concurrent session errors: {errors}"
    assert len(results) == 18

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_health_check_completes_quickly(db_session):
    start = time.monotonic()
    healthy = check_db_health(db_session)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert healthy is True
    assert elapsed_ms < 100
