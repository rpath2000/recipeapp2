"""
app.models.recipe
==================

SQLAlchemy ORM model for the Recipe entity.

Maps 1:1 to the RecipeOut / RecipeCreateIn / RecipeUpdateIn DTOs declared in
app.contracts. This module does not redefine those DTOs; conversion between
ORM instances and DTOs is the responsibility of the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base, get_db  # noqa: F401  (get_db re-exported per seam)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Recipe(Base):
    """Persisted recipe record."""

    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    ingredients: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index("ix_recipes_name", "name"),
        Index("ix_recipes_category", "category"),
        Index("ix_recipes_owner_id", "owner_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Recipe id={self.id} name={self.name!r} owner_id={self.owner_id!r}>"
