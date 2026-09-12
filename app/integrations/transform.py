"""Payload transformation between raw external dicts and RecipeData.

Centralizes mapping logic so the connector never has to reach into raw
dict payloads directly, and so validation errors are raised consistently
via the shared app.contracts.ValidationError.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.contracts import RecipeData, ValidationError

NAME_MAX_LENGTH = 120
INGREDIENTS_MAX_LENGTH = 4000


def to_recipe_data(raw: dict[str, Any]) -> RecipeData:
    """Transform a raw external payload dict into a validated RecipeData.

    Expected raw shape:
        {
            "id": "<uuid string or UUID>",
            "name": "<str>",
            "ingredients": "<str>",
            "created_at": "<iso8601 str or datetime>",
        }

    Raises:
        ValidationError: if required fields are missing, empty, or exceed
            declared length limits.
    """
    recipe_id = _parse_uuid(raw.get("id"))
    name = _require_str(raw.get("name"), field_name="name", max_length=NAME_MAX_LENGTH)
    ingredients = _require_str(
        raw.get("ingredients"),
        field_name="ingredients",
        max_length=INGREDIENTS_MAX_LENGTH,
    )
    created_at = _parse_datetime(raw.get("created_at"))

    return RecipeData(
        id=recipe_id,
        name=name,
        ingredients=ingredients,
        created_at=created_at,
    )


def from_recipe_data(recipe: RecipeData) -> dict[str, Any]:
    """Transform a RecipeData back into a JSON-serializable dict."""
    return {
        "id": str(recipe.id),
        "name": recipe.name,
        "ingredients": recipe.ingredients,
        "created_at": recipe.created_at.isoformat(),
    }


def _parse_uuid(value: Any) -> UUID:
    if value is None:
        raise ValidationError("id is required")
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError(f"id is not a valid UUID: {value!r}") from exc


def _require_str(value: Any, *, field_name: str, max_length: int) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    if len(value) > max_length:
        raise ValidationError(f"{field_name} must not exceed {max_length} characters")
    return value


def _parse_datetime(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"created_at is not a valid ISO8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
