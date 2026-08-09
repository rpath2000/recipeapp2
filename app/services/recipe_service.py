"""
RecipeService: business logic for recipe CRUD, search, filtering, pagination,
validation, ownership authorization, and image upload delegation.

This module intentionally has no FastAPI dependencies in its core logic so it
remains independently unit-testable. The REST handler (recipe_handler.py)
wires this service to HTTP concerns.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contracts import (
    RecipeCreateIn,
    RecipeListOut,
    RecipeOut,
    RecipeUpdateIn,
)
from app.models.recipe import Recipe
from app.services import audit
from app.services.image_service import ImageService

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
ENTITY_TYPE = "recipe"


class ValidationError(Exception):
    """Raised when input fails field-level validation."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class NotFoundError(Exception):
    """Raised when a requested recipe does not exist."""


class AuthorizationError(Exception):
    """Raised when the requesting user does not own the resource."""


def _require_non_blank(value: Optional[str], field_name: str) -> str:
    """Validate that a required string field is present and non-blank."""
    if value is None or not isinstance(value, str) or value.strip() == "":
        raise ValidationError(
            f"Field '{field_name}' is required and cannot be blank.",
            field=field_name,
        )
    return value.strip()


def _validate_create(recipe_in: RecipeCreateIn) -> None:
    """Validate all required fields for recipe creation."""
    _require_non_blank(recipe_in.name, "name")
    _require_non_blank(recipe_in.description, "description")
    _require_non_blank(recipe_in.ingredients, "ingredients")
    _require_non_blank(recipe_in.instructions, "instructions")
    _require_non_blank(recipe_in.category, "category")


def _validate_update(recipe_in: RecipeUpdateIn) -> None:
    """Validate all required fields for recipe update."""
    _require_non_blank(recipe_in.name, "name")
    _require_non_blank(recipe_in.description, "description")
    _require_non_blank(recipe_in.ingredients, "ingredients")
    _require_non_blank(recipe_in.instructions, "instructions")
    _require_non_blank(recipe_in.category, "category")


def _to_recipe_out(recipe: Recipe) -> RecipeOut:
    """Map an ORM Recipe model into the shared RecipeOut DTO."""
    return RecipeOut(
        id=str(recipe.id),
        name=recipe.name,
        description=recipe.description,
        ingredients=recipe.ingredients,
        instructions=recipe.instructions,
        category=recipe.category,
        image_url=recipe.image_url,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
        owner_id=str(recipe.owner_id),
    )


def _normalize_pagination(page: int, page_size: int) -> tuple[int, int]:
    """Clamp page and page_size to sane, safe bounds."""
    safe_page = page if page and page > 0 else 1
    safe_page_size = page_size if page_size and page_size > 0 else DEFAULT_PAGE_SIZE
    safe_page_size = min(safe_page_size, MAX_PAGE_SIZE)
    return safe_page, safe_page_size


def _paginate_query(query, page: int, page_size: int) -> RecipeListOut:
    """Execute a query with pagination and build a RecipeListOut."""
    safe_page, safe_page_size = _normalize_pagination(page, page_size)

    total = query.order_by(None).with_entities(func.count()).scalar() or 0
    total_pages = max(1, math.ceil(total / safe_page_size)) if total > 0 else 0

    offset = (safe_page - 1) * safe_page_size
    rows = (
        query.order_by(Recipe.created_at.desc())
        .offset(offset)
        .limit(safe_page_size)
        .all()
    )
    items = [_to_recipe_out(r) for r in rows]

    return RecipeListOut(
        items=items,
        total=total,
        page=safe_page,
        page_size=safe_page_size,
        total_pages=total_pages,
    )


class RecipeService:
    """
    Encapsulates recipe business logic: CRUD, search, filtering, pagination,
    validation, and ownership authorization. Delegates image storage concerns
    to ImageService.
    """

    def __init__(self, image_service: Optional[ImageService] = None) -> None:
        self._image_service = image_service or ImageService()

    def create_recipe(
        self, recipe_in: RecipeCreateIn, owner_id: str, db: Session
    ) -> RecipeOut:
        """
        Validate and persist a new recipe owned by owner_id.

        Raises:
            ValidationError: if any required field is blank.
        """
        if not owner_id or not owner_id.strip():
            raise ValidationError(
                "owner_id is required and cannot be blank.", field="owner_id"
            )

        _validate_create(recipe_in)

        recipe = Recipe(
            id=str(uuid.uuid4()),
            name=recipe_in.name.strip(),
            description=recipe_in.description.strip(),
            ingredients=recipe_in.ingredients.strip(),
            instructions=recipe_in.instructions.strip(),
            category=recipe_in.category.strip(),
            image_url=recipe_in.image_url,
            owner_id=owner_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(recipe)
        db.commit()
        db.refresh(recipe)

        audit.log_create(ENTITY_TYPE, str(recipe.id), owner_id)

        return _to_recipe_out(recipe)

    def get_recipe(self, recipe_id: str, db: Session) -> Optional[RecipeOut]:
        """Retrieve a recipe by id, returning None if not found."""
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if recipe is None:
            return None
        return _to_recipe_out(recipe)

    def list_recipes(
        self, page: int, page_size: int, db: Session
    ) -> RecipeListOut:
        """Return a paginated list of all recipes ordered by newest first."""
        query = db.query(Recipe)
        return _paginate_query(query, page, page_size)

    def update_recipe(
        self,
        recipe_id: str,
        recipe_in: RecipeUpdateIn,
        owner_id: str,
        db: Session,
    ) -> RecipeOut:
        """
        Validate and update an existing recipe. Only the owner may update.

        Raises:
            NotFoundError: if the recipe does not exist.
            AuthorizationError: if owner_id does not match the recipe owner.
            ValidationError: if any required field is blank.
        """
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if recipe is None:
            raise NotFoundError(f"Recipe with id '{recipe_id}' was not found.")

        if str(recipe.owner_id) != str(owner_id):
            audit.log_authorization_failure(
                ENTITY_TYPE, recipe_id, owner_id, "UPDATE", str(recipe.owner_id)
            )
            raise AuthorizationError(
                "You are not authorized to update this recipe."
            )

        _validate_update(recipe_in)

        recipe.name = recipe_in.name.strip()
        recipe.description = recipe_in.description.strip()
        recipe.ingredients = recipe_in.ingredients.strip()
        recipe.instructions = recipe_in.instructions.strip()
        recipe.category = recipe_in.category.strip()
        recipe.image_url = recipe_in.image_url
        recipe.updated_at = datetime.now(timezone.utc)

        db.add(recipe)
        db.commit()
        db.refresh(recipe)

        audit.log_update(ENTITY_TYPE, str(recipe.id), owner_id)

        return _to_recipe_out(recipe)

    def delete_recipe(self, recipe_id: str, owner_id: str, db: Session) -> None:
        """
        Delete a recipe. Only the owner may delete.

        Raises:
            NotFoundError: if the recipe does not exist.
            AuthorizationError: if owner_id does not match the recipe owner.
        """
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if recipe is None:
            raise NotFoundError(f"Recipe with id '{recipe_id}' was not found.")

        if str(recipe.owner_id) != str(owner_id):
            audit.log_authorization_failure(
                ENTITY_TYPE, recipe_id, owner_id, "DELETE", str(recipe.owner_id)
            )
            raise AuthorizationError(
                "You are not authorized to delete this recipe."
            )

        db.delete(recipe)
        db.commit()

        audit.log_delete(ENTITY_TYPE, recipe_id, owner_id)

    def search_recipes(
        self, query: str, page: int, page_size: int, db: Session
    ) -> RecipeListOut:
        """
        Perform a case-insensitive partial match search on recipe name.

        An empty/blank query returns an empty result set (no accidental
        full-table dump).
        """
        if query is None or query.strip() == "":
            return RecipeListOut(
                items=[], total=0, page=1, page_size=DEFAULT_PAGE_SIZE, total_pages=0
            )

        pattern = f"%{query.strip().lower()}%"
        db_query = db.query(Recipe).filter(func.lower(Recipe.name).like(pattern))
        return _paginate_query(db_query, page, page_size)

    def filter_recipes_by_category(
        self, category: str, page: int, page_size: int, db: Session
    ) -> RecipeListOut:
        """Return a paginated list of recipes matching the given category (case-insensitive)."""
        if category is None or category.strip() == "":
            return RecipeListOut(
                items=[], total=0, page=1, page_size=DEFAULT_PAGE_SIZE, total_pages=0
            )

        db_query = db.query(Recipe).filter(
            func.lower(Recipe.category) == category.strip().lower()
        )
        return _paginate_query(db_query, page, page_size)

    def upload_image(self, file: UploadFile, recipe_id: str) -> str:
        """Delegate image upload validation/storage to ImageService."""
        return self._image_service.upload_image(file, recipe_id)

    def get_image_url(self, recipe_id: str) -> Optional[str]:
        """Delegate image URL retrieval to ImageService."""
        return self._image_service.get_image_url(recipe_id)
