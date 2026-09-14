"""
Database layer: engine, declarative Base, ORM model(s), and the
get_db() session dependency.

Importable as `app.models.database`. Builds the engine from
app.db_url.DATABASE_URL (the single source of truth for the connection
string), never opening a connection at import time.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.db_url import DATABASE_URL

# Engine and sessionmaker are constructed eagerly (safe: no connection is
# opened until a query actually runs), but no connect/execute happens here.
engine = create_engine(DATABASE_URL, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


class Recipe(Base):
    """Recipe ORM model.

    Fields (DR-001..DR-004):
      - id: SERIAL PRIMARY KEY
      - name: VARCHAR(120)
      - ingredients: TEXT (whitespace/line breaks preserved)
      - created_at: TIMESTAMP, auto-populated on INSERT
    """

    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    ingredients = Column(Text, nullable=False)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=None,
        default=lambda: datetime.now(timezone.utc),
    )


def get_db():
    """FastAPI dependency yielding a SQLAlchemy Session scoped to the
    request lifecycle, closing it when the request completes."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
