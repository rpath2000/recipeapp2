"""REST handler exposing RecipeService over JSON.

This router owns its own API prefix (/api/recipes) — it does NOT declare
/recipe or /recipes/{id} page routes, which belong to app.web's
server-rendered pages.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.contracts import ValidationError
from app.models import get_db
from app.services import RecipeService

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


class RecipeCreateRequest(BaseModel):
    name: str
    ingredients: str


class RecipeUpdateRequest(BaseModel):
    name: str
    ingredients: str


class RecipeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ingredients: str
    created_at: datetime


def _service(db: Session = Depends(get_db)) -> RecipeService:
    return RecipeService(db)


@router.post("", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
def create_recipe(
    payload: RecipeCreateRequest, service: RecipeService = Depends(_service)
) -> RecipeResponse:
    try:
        dto = service.create(name=payload.name, ingredients=payload.ingredients)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
    return RecipeResponse.model_validate(dto)


@router.put("/{recipe_id}", response_model=RecipeResponse)
def update_recipe(
    recipe_id: int,
    payload: RecipeUpdateRequest,
    service: RecipeService = Depends(_service),
) -> RecipeResponse:
    try:
        dto = service.update(
            recipe_id=recipe_id, name=payload.name, ingredients=payload.ingredients
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return RecipeResponse.model_validate(dto)


@router.get("/{recipe_id}", response_model=RecipeResponse)
def get_recipe(
    recipe_id: int, service: RecipeService = Depends(_service)
) -> RecipeResponse:
    dto = service.get_by_id(recipe_id)
    if dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe with id {recipe_id} not found.",
        )
    return RecipeResponse.model_validate(dto)


@router.get("", response_model=list[RecipeResponse])
def list_recipes(service: RecipeService = Depends(_service)) -> list[RecipeResponse]:
    dtos = service.list_all()
    return [RecipeResponse.model_validate(dto) for dto in dtos]
