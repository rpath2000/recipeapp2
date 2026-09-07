"""REST handler exposing recipe CRUD operations under /api/recipes.

This module wires HTTP concerns (status codes, request/response
schemas) to the RecipeService business logic. It intentionally does
NOT declare page routes such as GET/POST /recipe/{id} -- those are
owned by app.web.pages.

Traceability: FRS-003, FRS-004, FRS-005, FRS-009, FRS-013, FRS-017.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.contracts import (
    RecipeCreateDTO,
    RecipeDTO,
    RecipeNotFoundError,
    RecipeUpdateDTO,
    ValidationError,
)
from app.models import get_db
from app.services.recipe_service import RecipeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


class RecipeCreateRequest(BaseModel):
    """Request body for creating a recipe."""

    name: str = Field(..., description="Recipe name.")
    ingredients: str = Field(..., description="Recipe ingredients.")


class RecipeUpdateRequest(BaseModel):
    """Request body for updating a recipe."""

    name: str = Field(..., description="Recipe name.")
    ingredients: str = Field(..., description="Recipe ingredients.")


class RecipeResponse(BaseModel):
    """Response body representing a single recipe."""

    id: int
    name: str
    ingredients: str
    created_at: str
    updated_at: str

    @staticmethod
    def from_dto(dto: RecipeDTO) -> "RecipeResponse":
        return RecipeResponse(
            id=dto.id,
            name=dto.name,
            ingredients=dto.ingredients,
            created_at=dto.created_at.isoformat(),
            updated_at=dto.updated_at.isoformat(),
        )


class RecipeCreateResponse(BaseModel):
    """Response body returned after successfully creating a recipe."""

    id: int


def _get_recipe_service(db: Session = Depends(get_db)) -> RecipeService:
    """Construct a RecipeService bound to the request-scoped session.

    Never instantiate RecipeService at import time; it must be built
    per-request with the injected session.
    """
    return RecipeService(db)


def _validation_error_response(exc: ValidationError) -> HTTPException:
    """Translate a ValidationError into an HTTP 422 response."""
    errors = getattr(exc, "errors", None)
    if not isinstance(errors, dict):
        errors = {"detail": str(exc)}
    logger.info("Recipe validation failed: %s", errors)
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"message": "Validation failed.", "errors": errors},
    )


@router.post("", response_model=RecipeCreateResponse, status_code=status.HTTP_201_CREATED)
def create_recipe(
    payload: RecipeCreateRequest,
    service: RecipeService = Depends(_get_recipe_service),
) -> RecipeCreateResponse:
    """Create a new recipe.

    Returns 201 with the new recipe id, or 422 with field-specific
    validation errors.
    """
    try:
        new_id = service.create(
            RecipeCreateDTO(name=payload.name, ingredients=payload.ingredients)
        )
    except ValidationError as exc:
        raise _validation_error_response(exc) from exc

    return RecipeCreateResponse(id=new_id)


@router.put("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_recipe(
    recipe_id: str,
    payload: RecipeUpdateRequest,
    service: RecipeService = Depends(_get_recipe_service),
) -> None:
    """Update an existing recipe.

    Returns 204 on success, 404 if the id is malformed or not found,
    422 on validation failure.
    """
    try:
        service.update(
            recipe_id,
            RecipeUpdateDTO(name=payload.name, ingredients=payload.ingredients),
        )
    except ValidationError as exc:
        raise _validation_error_response(exc) from exc
    except RecipeNotFoundError as exc:
        logger.info("Recipe not found for update: %s", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe not found.",
        ) from exc


@router.get("/{recipe_id}", response_model=RecipeResponse)
def get_recipe(
    recipe_id: str,
    service: RecipeService = Depends(_get_recipe_service),
) -> RecipeResponse:
    """Fetch a single recipe by id.

    Returns 200 with the recipe, or 404 if the id is malformed or not
    found.
    """
    try:
        dto = service.get_by_id(recipe_id)
    except RecipeNotFoundError as exc:
        logger.info("Recipe not found: %s", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe not found.",
        ) from exc

    return RecipeResponse.from_dto(dto)


@router.get("", response_model=list[RecipeResponse])
def list_recipes(
    service: RecipeService = Depends(_get_recipe_service),
) -> list[RecipeResponse]:
    """List all recipes ordered by updated_at DESC, id DESC."""
    dtos = service.list_all()
    return [RecipeResponse.from_dto(dto) for dto in dtos]
