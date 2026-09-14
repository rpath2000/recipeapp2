"""Recipe business logic service.

Implements validation and persistence logic for Recipe entities. This
module owns no database schema (that belongs to app.models) and no HTTP
concerns (that belongs to the REST handler) — it is the business-logic
layer that sits between them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import RecipeData, ValidationError
from app.models import Recipe

NAME_MAX_LENGTH = 120
INGREDIENTS_MAX_LENGTH = 4000


class RecipeService:
    """Encapsulates create/update/read operations for Recipe entities.

    Constructed per-request with a database session:

        service = RecipeService(db)

    Never instantiate this at module import time — it must be built inside
    the function/handler that owns the session's lifecycle.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_name(name: str) -> str:
        stripped = (name or "").strip()
        if not stripped:
            raise ValidationError(field="name", message="Name must not be empty.")
        if len(stripped) > NAME_MAX_LENGTH:
            raise ValidationError(
                field="name",
                message=f"Name must be at most {NAME_MAX_LENGTH} characters.",
            )
        return stripped

    @staticmethod
    def _validate_ingredients(ingredients: str) -> str:
        stripped = (ingredients or "").strip()
        if not stripped:
            raise ValidationError(
                field="ingredients", message="Ingredients must not be empty."
            )
        if len(stripped) > INGREDIENTS_MAX_LENGTH:
            raise ValidationError(
                field="ingredients",
                message=f"Ingredients must be at most {INGREDIENTS_MAX_LENGTH} characters.",
            )
        return stripped

    @staticmethod
    def _to_dto(recipe: Recipe) -> RecipeData:
        return RecipeData(
            id=recipe.id,
            name=recipe.name,
            ingredients=recipe.ingredients,
            created_at=recipe.created_at,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def create(self, name: str, ingredients: str) -> RecipeData:
        """Validate and persist a new recipe, returning its DTO."""
        valid_name = self._validate_name(name)
        valid_ingredients = self._validate_ingredients(ingredients)

        recipe = Recipe(name=valid_name, ingredients=valid_ingredients)
        self._db.add(recipe)
        self._db.commit()
        self._db.refresh(recipe)
        return self._to_dto(recipe)

    def update(self, recipe_id: int, name: str, ingredients: str) -> RecipeData:
        """Validate and persist changes to an existing recipe.

        Raises:
            ValidationError: if name/ingredients are invalid.
            LookupError: if no recipe with the given id exists.
        """
        valid_name = self._validate_name(name)
        valid_ingredients = self._validate_ingredients(ingredients)

        recipe = self._db.get(Recipe, recipe_id)
        if recipe is None:
            raise LookupError(f"Recipe with id {recipe_id} does not exist.")

        recipe.name = valid_name
        recipe.ingredients = valid_ingredients
        self._db.commit()
        self._db.refresh(recipe)
        return self._to_dto(recipe)

    def get_by_id(self, recipe_id: int) -> RecipeData | None:
        """Return the recipe DTO for recipe_id, or None if it doesn't exist."""
        recipe = self._db.get(Recipe, recipe_id)
        if recipe is None:
            return None
        return self._to_dto(recipe)

    def list_all(self) -> list[RecipeData]:
        """Return all recipes ordered by created_at descending (newest first)."""
        stmt = select(Recipe).order_by(Recipe.created_at.desc())
        recipes = self._db.execute(stmt).scalars().all()
        return [self._to_dto(r) for r in recipes]
