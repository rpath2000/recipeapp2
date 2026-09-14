"""Business logic services for recipe management.

Exposes RecipeService, the single entry point for recipe CRUD operations,
validation, and retrieval used by the REST handlers in app.web.
"""
from app.services.service import RecipeService

__all__ = ["RecipeService"]
