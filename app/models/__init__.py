"""
app.models package.

Exposes the shared declarative Base, the Recipe ORM model, and the
get_db() session dependency, re-exported from database.py so other
components can do `from app.models import Base, Recipe, get_db`.
"""

from app.models.database import Base, Recipe, get_db

__all__ = ["Base", "Recipe", "get_db"]
