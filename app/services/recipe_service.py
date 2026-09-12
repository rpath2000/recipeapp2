"""Business logic for Recipe CRUD operations.

This module implements the RecipeService, which owns validation and
persistence logic for Recipe entities. It relies on the shared ORM model
(app.models.Recipe) for storage and the shared DTO (app.contracts.RecipeData)
for its return values.
"""

from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.contracts import RecipeData, ValidationError
from app.models import Recipe

NAME_MIN_LENGTH = 1
NAME_MAX_LENGTH = 120
INGREDIENTS_MIN_LENGTH = 1
INGREDIENTS_MAX_LENGTH = 4000


class RecipeService:
    """Encapsulates validation and persistence logic for Recipe entities."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_recipe(self, name: str, ingredients: str) -> RecipeData:
        """Validate input and persist a new Recipe, returning its DTO."""
        clean_name = self._validate_name(name)
        clean_ingredients = self._validate_ingredients(ingredients)

        recipe = Recipe(
            id=uuid4(),
            name=clean_name,
            ingredients=clean_ingredients,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(recipe)
        self._db.commit()
        self._db.refresh(recipe)

        return self._to_dto(recipe)

    def update_recipe(self, recipe_id: UUID, name: str, ingredients: str) -> RecipeData:
        """Validate input and update an existing Recipe by id.

        Raises:
            ValidationError: if the input fails validation rules.
            ValueError: if no Recipe with the given id exists.
        """
        clean_name = self._validate_name(name)
        clean_ingredients = self._validate_ingredients(ingredients)

        recipe = self._db.query(Recipe).filter(Recipe.id == recipe_id).one_or_none()
        if recipe is None:
            raise ValueError(f"Recipe with id {recipe_id} does not exist")

        recipe.name = clean_name
        recipe.ingredients = clean_ingredients
        self._db.commit()
        self._db.refresh(recipe)

        return self._to_dto(recipe)

    def get_recipe_by_id(self, recipe_id: UUID) -> RecipeData | None:
        """Return the RecipeData DTO for the given id, or None if not found."""
        recipe = self._db.query(Recipe).filter(Recipe.id == recipe_id).one_or_none()
        if recipe is None:
            return None
        return self._to_dto(recipe)

    def list_recipes(self) -> list[RecipeData]:
        """Return all recipes ordered by created_at descending (newest first)."""
        recipes = (
            self._db.query(Recipe)
            .order_by(Recipe.created_at.desc())
            .all()
        )
        return [self._to_dto(recipe) for recipe in recipes]

    @staticmethod
    def _validate_name(name: str) -> str:
        if name is None:
            raise ValidationError("Recipe name must not be empty.")
        stripped = name.strip()
        if len(stripped) < NAME_MIN_LENGTH:
            raise ValidationError("Recipe name must not be empty.")
        if len(name) > NAME_MAX_LENGTH:
            raise ValidationError(
                f"Recipe name must not exceed {NAME_MAX_LENGTH} characters."
            )
        return name

    @staticmethod
    def _validate_ingredients(ingredients: str) -> str:
        if ingredients is None:
            raise ValidationError("Recipe ingredients must not be empty.")
        stripped = ingredients.strip()
        if len(stripped) < INGREDIENTS_MIN_LENGTH:
            raise ValidationError("Recipe ingredients must not be empty.")
        if len(ingredients) > INGREDIENTS_MAX_LENGTH:
            raise ValidationError(
                f"Recipe ingredients must not exceed {INGREDIENTS_MAX_LENGTH} characters."
            )
        return ingredients

    @staticmethod
    def _to_dto(recipe: Recipe) -> RecipeData:
        return RecipeData(
            id=recipe.id,
            name=recipe.name,
            ingredients=recipe.ingredients,
            created_at=recipe.created_at,
        )
