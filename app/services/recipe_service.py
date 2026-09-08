"""Seam module exposing `RecipeService` at `app.services.recipe_service`.

The canonical implementation lives in `app.services.recipe`. This module
re-exports it so callers can import `RecipeService` from either location.
"""

from __future__ import annotations

from app.services.recipe import RecipeService

__all__ = ["RecipeService"]
