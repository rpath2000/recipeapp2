"""Recipe ORM model."""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeDecorator, CHAR

from app.models.base import Base


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type when available, otherwise stores as CHAR(36).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


class Recipe(Base):
    """A saved recipe consisting of a name and a list of ingredients."""

    __tablename__ = "recipes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, nullable=False)
    name = Column(String(120), nullable=False)
    ingredients = Column(Text(4000), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=None).astimezone()
    )

    def __repr__(self) -> str:
        return f"<Recipe id={self.id!r} name={self.name!r}>"
