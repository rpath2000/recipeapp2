"""app.models package.

Exposes the declarative Base, ORM models, and the get_db session
dependency as the shared seams for migration and service-layer
consumption.
"""
from app.models.database import Base, Recipe, get_db

__all__ = ["Base", "Recipe", "get_db"]
