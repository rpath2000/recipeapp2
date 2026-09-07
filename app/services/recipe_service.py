"""Business logic for recipe CRUD operations.

This module implements the RecipeService, which owns validation,
sanitization, persistence orchestration (via the shared SQLAlchemy
session), and ordering rules for the recipe dashboard.

Traceability:
    FRS-003: name validation (1-120 chars after trim, non-empty)
    FRS-004: ingredients validation (1-4000 chars after trim, non-empty)
    FRS-005: strip non-printable control characters except newline/tab
    FRS-009: list_all ordered by updated_at DESC, id DESC
    FRS-013: ValidationError carries field-specific messages
    FRS-017: RecipeNotFoundError for non-existent or malformed ids
"""

from __future__ import annotations

import unicodedata

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.contracts import (
    RecipeCreateDTO,
    RecipeDTO,
    RecipeNotFoundError,
    RecipeUpdateDTO,
    ValidationError,
)
from app.models import Recipe

# Field length constraints per FRS-003 / FRS-004.
_NAME_MIN_LENGTH = 1
_NAME_MAX_LENGTH = 120
_INGREDIENTS_MIN_LENGTH = 1
_INGREDIENTS_MAX_LENGTH = 4000

# Characters that must always be preserved even though they are
# technically control characters (category "Cc").
_ALLOWED_CONTROL_CHARS = {"\n", "\t"}


def _strip_control_characters(value: str) -> str:
    """Remove non-printable control characters from ``value``.

    Preserves newline (\\n) and tab (\\t) characters per FRS-005.
    All other Unicode "control" category characters (category "Cc"),
    including carriage return, NUL, and other C0/C1 control codes,
    are removed.

    Args:
        value: The raw string to sanitize.

    Returns:
        The sanitized string with disallowed control characters removed.
    """
    return "".join(
        char
        for char in value
        if char in _ALLOWED_CONTROL_CHARS or unicodedata.category(char) != "Cc"
    )


def _validate_and_sanitize(name: str, ingredients: str) -> tuple[str, str]:
    """Validate and sanitize recipe fields.

    Args:
        name: Raw recipe name.
        ingredients: Raw recipe ingredients text.

    Returns:
        A tuple of (sanitized_name, sanitized_ingredients).

    Raises:
        ValidationError: If one or both fields fail validation, with a
            dict mapping field name to a specific error message.
    """
    errors: dict[str, str] = {}

    # Sanitize first (control-char stripping), then trim for validation,
    # per FRS-005 followed by FRS-003/FRS-004.
    sanitized_name = _strip_control_characters(name if name is not None else "")
    sanitized_ingredients = _strip_control_characters(
        ingredients if ingredients is not None else ""
    )

    trimmed_name = sanitized_name.strip()
    trimmed_ingredients = sanitized_ingredients.strip()

    if len(trimmed_name) < _NAME_MIN_LENGTH:
        errors["name"] = "Name must not be empty."
    elif len(trimmed_name) > _NAME_MAX_LENGTH:
        errors["name"] = (
            f"Name must be at most {_NAME_MAX_LENGTH} characters after trimming."
        )

    if len(trimmed_ingredients) < _INGREDIENTS_MIN_LENGTH:
        errors["ingredients"] = "Ingredients must not be empty."
    elif len(trimmed_ingredients) > _INGREDIENTS_MAX_LENGTH:
        errors["ingredients"] = (
            f"Ingredients must be at most {_INGREDIENTS_MAX_LENGTH} characters "
            "after trimming."
        )

    if errors:
        raise ValidationError(errors)

    # Store the trimmed, sanitized values.
    return trimmed_name, trimmed_ingredients


def _to_dto(recipe: Recipe) -> RecipeDTO:
    """Map an ORM ``Recipe`` row to a ``RecipeDTO``."""
    return RecipeDTO(
        id=recipe.id,
        name=recipe.name,
        ingredients=recipe.ingredients,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


def _parse_recipe_id(recipe_id: object) -> int:
    """Parse and validate a recipe identifier.

    Accepts ints directly. Rejects non-numeric, empty, negative, or
    otherwise malformed identifiers per FRS-017.

    Args:
        recipe_id: The candidate identifier.

    Returns:
        A validated positive integer id.

    Raises:
        RecipeNotFoundError: If the id is malformed (not a valid
            positive integer).
    """
    if isinstance(recipe_id, bool):
        # bool is a subclass of int; explicitly reject to avoid
        # surprising True/False being treated as 1/0.
        raise RecipeNotFoundError(f"Malformed recipe id: {recipe_id!r}")

    if isinstance(recipe_id, int):
        parsed = recipe_id
    elif isinstance(recipe_id, str):
        stripped = recipe_id.strip()
        if not stripped or not stripped.lstrip("-").isdigit():
            raise RecipeNotFoundError(f"Malformed recipe id: {recipe_id!r}")
        try:
            parsed = int(stripped)
        except ValueError as exc:
            raise RecipeNotFoundError(
                f"Malformed recipe id: {recipe_id!r}"
            ) from exc
    else:
        raise RecipeNotFoundError(f"Malformed recipe id: {recipe_id!r}")

    if parsed <= 0:
        raise RecipeNotFoundError(f"Malformed recipe id: {recipe_id!r}")

    return parsed


class RecipeService:
    """Encapsulates recipe CRUD business logic.

    Instances are constructed per-request with an injected SQLAlchemy
    ``Session`` (see ``app.models.get_db``). Never instantiate this
    class at module import time.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, data: RecipeCreateDTO) -> int:
        """Create a new recipe.

        Args:
            data: The recipe fields to create.

        Returns:
            The newly created recipe's id.

        Raises:
            ValidationError: If name or ingredients fail validation.
        """
        name, ingredients = _validate_and_sanitize(data.name, data.ingredients)

        recipe = Recipe(name=name, ingredients=ingredients)
        self._db.add(recipe)
        self._db.commit()
        self._db.refresh(recipe)

        return recipe.id

    def update(self, recipe_id: int, data: RecipeUpdateDTO) -> None:
        """Update an existing recipe.

        Args:
            recipe_id: The id of the recipe to update.
            data: The new field values.

        Raises:
            RecipeNotFoundError: If the id is malformed or does not
                correspond to an existing recipe.
            ValidationError: If name or ingredients fail validation.
        """
        parsed_id = _parse_recipe_id(recipe_id)

        # Validate before touching the database so that invalid input
        # never triggers a partial update.
        name, ingredients = _validate_and_sanitize(data.name, data.ingredients)

        recipe = self._db.query(Recipe).filter(Recipe.id == parsed_id).first()
        if recipe is None:
            raise RecipeNotFoundError(f"Recipe not found for id: {recipe_id!r}")

        recipe.name = name
        recipe.ingredients = ingredients
        self._db.commit()

    def get_by_id(self, recipe_id: int) -> RecipeDTO:
        """Retrieve a recipe by id.

        Args:
            recipe_id: The id of the recipe to fetch.

        Returns:
            The matching RecipeDTO.

        Raises:
            RecipeNotFoundError: If the id is malformed or does not
                correspond to an existing recipe.
        """
        parsed_id = _parse_recipe_id(recipe_id)

        recipe = self._db.query(Recipe).filter(Recipe.id == parsed_id).first()
        if recipe is None:
            raise RecipeNotFoundError(f"Recipe not found for id: {recipe_id!r}")

        return _to_dto(recipe)

    def list_all(self) -> list[RecipeDTO]:
        """List all recipes for the dashboard.

        Returns:
            All recipes ordered by updated_at DESC, id DESC (FRS-009),
            with no pagination applied.
        """
        recipes = (
            self._db.query(Recipe)
            .order_by(desc(Recipe.updated_at), desc(Recipe.id))
            .all()
        )
        return [_to_dto(recipe) for recipe in recipes]
