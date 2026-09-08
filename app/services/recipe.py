"""Recipe business-logic service.

Implements CRUD operations for recipes with server-side validation of
the `name` and `ingredients` fields. This module is the sole owner of
recipe business logic; persistence uses the shared `Recipe` ORM model
declared in `app.models`.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.contracts import RecipeDTO, ValidationError
from app.models import Recipe

NAME_MAX_LENGTH = 120
INGREDIENTS_MAX_LENGTH = 4000


def _validate_name(name: str) -> str:
    """Validate and normalize the recipe name.

    Args:
        name: Raw name input.

    Returns:
        The trimmed, validated name.

    Raises:
        ValidationError: If the trimmed name is empty or exceeds the
            maximum allowed length.
    """
    trimmed = (name or "").strip()
    if not trimmed:
        raise ValidationError("name must not be empty")
    if len(trimmed) > NAME_MAX_LENGTH:
        raise ValidationError(
            f"name must be at most {NAME_MAX_LENGTH} characters"
        )
    return trimmed


def _validate_ingredients(ingredients: str) -> str:
    """Validate and normalize the recipe ingredients.

    Args:
        ingredients: Raw ingredients input.

    Returns:
        The trimmed, validated ingredients text.

    Raises:
        ValidationError: If the trimmed ingredients text is empty or
            exceeds the maximum allowed length.
    """
    trimmed = (ingredients or "").strip()
    if not trimmed:
        raise ValidationError("ingredients must not be empty")
    if len(trimmed) > INGREDIENTS_MAX_LENGTH:
        raise ValidationError(
            f"ingredients must be at most {INGREDIENTS_MAX_LENGTH} characters"
        )
    return trimmed


def _to_dto(recipe: Recipe) -> RecipeDTO:
    """Map a persisted `Recipe` ORM row into a `RecipeDTO`."""
    return RecipeDTO(
        id=recipe.id,
        name=recipe.name,
        ingredients=recipe.ingredients,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


class RecipeService:
    """Encapsulates CRUD operations and validation for recipes."""

    def create_recipe(self, name: str, ingredients: str, db: Session) -> RecipeDTO:
        """Create a new recipe.

        Args:
            name: The recipe name (validated: 1-120 chars, trimmed).
            ingredients: The recipe ingredients (validated: 1-4000 chars, trimmed).
            db: Active database session.

        Returns:
            The created recipe as a `RecipeDTO`.

        Raises:
            ValidationError: If `name` or `ingredients` fail validation.
        """
        valid_name = _validate_name(name)
        valid_ingredients = _validate_ingredients(ingredients)

        recipe = Recipe(name=valid_name, ingredients=valid_ingredients)
        db.add(recipe)
        db.commit()
        db.refresh(recipe)

        return _to_dto(recipe)

    def get_recipe(self, id: int, db: Session) -> RecipeDTO | None:
        """Retrieve a recipe by id.

        Args:
            id: The recipe's primary key.
            db: Active database session.

        Returns:
            The matching `RecipeDTO`, or `None` if no such recipe exists.
        """
        recipe = db.query(Recipe).filter(Recipe.id == id).first()
        if recipe is None:
            return None
        return _to_dto(recipe)

    def update_recipe(
        self, id: int, name: str, ingredients: str, db: Session
    ) -> RecipeDTO:
        """Update an existing recipe.

        Args:
            id: The recipe's primary key.
            name: The new recipe name (validated: 1-120 chars, trimmed).
            ingredients: The new ingredients (validated: 1-4000 chars, trimmed).
            db: Active database session.

        Returns:
            The updated recipe as a `RecipeDTO`.

        Raises:
            ValidationError: If `name` or `ingredients` fail validation, or
                if no recipe with the given id exists.
        """
        valid_name = _validate_name(name)
        valid_ingredients = _validate_ingredients(ingredients)

        recipe = db.query(Recipe).filter(Recipe.id == id).first()
        if recipe is None:
            raise ValidationError(f"recipe with id {id} does not exist")

        recipe.name = valid_name
        recipe.ingredients = valid_ingredients

        db.add(recipe)
        db.commit()
        db.refresh(recipe)

        return _to_dto(recipe)

    def list_recipes(self, db: Session) -> list[RecipeDTO]:
        """List all recipes ordered by most recently updated first.

        Args:
            db: Active database session.

        Returns:
            All recipes, ordered by `updated_at` descending, then `id`
            descending to break ties deterministically.
        """
        recipes = (
            db.query(Recipe)
            .order_by(Recipe.updated_at.desc(), Recipe.id.desc())
            .all()
        )
        return [_to_dto(recipe) for recipe in recipes]
