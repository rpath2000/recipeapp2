"""
Payload transformation/mapping between the application's shared
RecipeDTO contracts and the outbound wire format used by connector.py.

Keeps mapping logic isolated and pure (no I/O) so it can be unit tested
independently of the connector and any HTTP transport.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.contracts import RecipeCreateDTO, RecipeDTO, ValidationError

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


def recipe_dto_to_outbound_payload(recipe: RecipeDTO) -> dict[str, Any]:
    """Map a RecipeDTO to the JSON payload shape expected downstream.

    Raises:
        ValidationError: if required fields are missing or malformed.
    """
    if not isinstance(recipe, RecipeDTO):
        raise ValidationError("recipe must be a RecipeDTO instance")

    if not recipe.name or not recipe.name.strip():
        raise ValidationError("recipe.name must not be empty")

    if not recipe.ingredients or not recipe.ingredients.strip():
        raise ValidationError("recipe.ingredients must not be empty")

    return {
        "id": recipe.id,
        "attributes": {
            "name": recipe.name.strip(),
            "ingredients": _split_ingredients(recipe.ingredients),
        },
        "metadata": {
            "created_at": _to_iso(recipe.created_at),
            "updated_at": _to_iso(recipe.updated_at),
        },
    }


def recipe_create_dto_to_outbound_payload(recipe: RecipeCreateDTO) -> dict[str, Any]:
    """Map a RecipeCreateDTO (no id/timestamps yet) to an outbound payload."""
    if not isinstance(recipe, RecipeCreateDTO):
        raise ValidationError("recipe must be a RecipeCreateDTO instance")

    if not recipe.name or not recipe.name.strip():
        raise ValidationError("recipe.name must not be empty")

    if not recipe.ingredients or not recipe.ingredients.strip():
        raise ValidationError("recipe.ingredients must not be empty")

    return {
        "attributes": {
            "name": recipe.name.strip(),
            "ingredients": _split_ingredients(recipe.ingredients),
        }
    }


def outbound_response_to_dict(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize an outbound API JSON response body into a plain dict.

    Defensive mapping: tolerates missing optional fields, never raises
    on absent keys.
    """
    if not isinstance(body, dict):
        raise ValidationError("outbound response body must be a JSON object")

    return {
        "id": body.get("id"),
        "name": body.get("attributes", {}).get("name") if isinstance(body.get("attributes"), dict) else None,
        "ingredients": ", ".join(body.get("attributes", {}).get("ingredients", []))
        if isinstance(body.get("attributes"), dict)
        else None,
        "status": body.get("status", "unknown"),
    }


def _split_ingredients(ingredients: str) -> list[str]:
    return [item.strip() for item in ingredients.split(",") if item.strip()]


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
