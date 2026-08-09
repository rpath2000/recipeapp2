"""
REST handler exposing recipe CRUD, search, filter, pagination, and image
upload endpoints. Wires RecipeService/ImageService business logic to HTTP
concerns: request parsing, status codes, and authentication/authorization
via the shared SSO middleware.

This router is intentionally self-contained within app/services so it can be
composed by the application entrypoint without introducing cross-directory
edits.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.contracts import RecipeCreateIn, RecipeListOut, RecipeOut, RecipeUpdateIn
from app.models.database import get_db
from app.security.sso_middleware import SSOMiddleware
from app.services.image_service import ImageValidationError
from app.services.recipe_service import (
    AuthorizationError,
    NotFoundError,
    RecipeService,
    ValidationError,
)

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

_recipe_service = RecipeService()
_sso = SSOMiddleware()


def get_recipe_service() -> RecipeService:
    """Dependency provider for RecipeService, overridable in tests."""
    return _recipe_service


def get_current_user_id(request: Request) -> str:
    """Resolve the authenticated user id from the shared SSO middleware."""
    return _sso.get_current_user(request)


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(
    recipe_in: RecipeCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    service: RecipeService = Depends(get_recipe_service),
) -> RecipeOut:
    """Create a new recipe owned by the authenticated user."""
    owner_id = get_current_user_id(request)
    try:
        return service.create_recipe(recipe_in, owner_id, db)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(
    recipe_id: str,
    db: Session = Depends(get_db),
    service: RecipeService = Depends(get_recipe_service),
) -> RecipeOut:
    """Retrieve a single recipe by id."""
    recipe = service.get_recipe(recipe_id, db)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found."
        )
    return recipe


@router.get("", response_model=RecipeListOut)
def list_recipes(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    service: RecipeService = Depends(get_recipe_service),
) -> RecipeListOut:
    """List recipes with pagination."""
    return service.list_recipes(page, page_size, db)


@router.get("/search/by-name", response_model=RecipeListOut)
def search_recipes(
    q: str,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    service: RecipeService = Depends(get_recipe_service),
) -> RecipeListOut:
    """Case-insensitive partial-match search on recipe name."""
    return service.search_recipes(q, page, page_size, db)


@router.get("/filter/by-category", response_model=RecipeListOut)
def filter_recipes(
    category: str,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    service: RecipeService = Depends(get_recipe_service),
) -> RecipeListOut:
    """Filter recipes by exact (case-insensitive) category match, paginated."""
    return service.filter_recipes_by_category(category, page, page_size, db)


@router.put("/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: str,
    recipe_in: RecipeUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    service: RecipeService = Depends(get_recipe_service),
) -> RecipeOut:
    """Update an existing recipe. Only the owner may perform this action."""
    owner_id = get_current_user_id(request)
    try:
        return service.update_recipe(recipe_id, recipe_in, owner_id, db)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: str,
    request: Request,
    db: Session = Depends(get_db),
    service: RecipeService = Depends(get_recipe_service),
) -> None:
    """Delete a recipe. Only the owner may perform this action."""
    owner_id = get_current_user_id(request)
    try:
        service.delete_recipe(recipe_id, owner_id, db)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post("/{recipe_id}/image", status_code=status.HTTP_201_CREATED)
def upload_recipe_image(
    recipe_id: str,
    file: UploadFile = File(...),
    service: RecipeService = Depends(get_recipe_service),
) -> dict:
    """Upload an image for a recipe. Validates size (<=5MB) and format."""
    try:
        url = service.upload_image(file, recipe_id)
    except ImageValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return {"image_url": url}


@router.get("/{recipe_id}/image")
def get_recipe_image(
    recipe_id: str,
    service: RecipeService = Depends(get_recipe_service),
) -> dict:
    """Retrieve the image URL for a recipe, if any."""
    url: Optional[str] = service.get_image_url(recipe_id)
    return {"image_url": url}
