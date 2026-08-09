"""
Recipe REST API router (v1).

Exposes CRUD, search, filter, and image endpoints for recipes.
Delegates all business logic to RecipeService and enforces
authentication/ownership via the SSO auth dependency.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.contracts import RecipeCreateIn, RecipeListOut, RecipeOut, RecipeUpdateIn
from app.models.database import get_db
from app.security.authz import get_current_user, verify_ownership
from app.services.recipe_service import RecipeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recipes", tags=["recipes"])

_service = RecipeService()


def _not_found(recipe_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "not_found", "message": f"Recipe '{recipe_id}' was not found."},
    )


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "forbidden", "message": "You do not have permission to modify this recipe."},
    )


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(
    recipe_in: RecipeCreateIn,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeOut:
    try:
        return _service.create_recipe(recipe_in=recipe_in, owner_id=user_id, db=db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create recipe for owner_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "Unable to create recipe."},
        )


@router.get("", response_model=RecipeListOut)
def list_recipes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeListOut:
    try:
        return _service.list_recipes(page=page, page_size=page_size, db=db)
    except Exception:
        logger.exception("Failed to list recipes page=%s page_size=%s", page, page_size)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "Unable to list recipes."},
        )


@router.get("/search", response_model=RecipeListOut)
def search_recipes(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeListOut:
    try:
        return _service.search_recipes(query=q, page=page, page_size=page_size, db=db)
    except Exception:
        logger.exception("Failed to search recipes query=%s", q)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "Unable to search recipes."},
        )


@router.get("/filter", response_model=RecipeListOut)
def filter_recipes(
    category: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeListOut:
    try:
        return _service.filter_recipes_by_category(category=category, page=page, page_size=page_size, db=db)
    except Exception:
        logger.exception("Failed to filter recipes category=%s", category)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "Unable to filter recipes."},
        )


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeOut:
    recipe = _service.get_recipe(recipe_id=recipe_id, db=db)
    if recipe is None:
        raise _not_found(recipe_id)
    return recipe


@router.put("/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: str,
    recipe_in: RecipeUpdateIn,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeOut:
    existing = _service.get_recipe(recipe_id=recipe_id, db=db)
    if existing is None:
        raise _not_found(recipe_id)
    if not verify_ownership(existing.owner_id, user_id):
        raise _forbidden()

    try:
        return _service.update_recipe(recipe_id=recipe_id, recipe_in=recipe_in, owner_id=user_id, db=db)
    except HTTPException:
        raise
    except PermissionError:
        raise _forbidden()
    except Exception:
        logger.exception("Failed to update recipe_id=%s", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "Unable to update recipe."},
        )


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    existing = _service.get_recipe(recipe_id=recipe_id, db=db)
    if existing is None:
        raise _not_found(recipe_id)
    if not verify_ownership(existing.owner_id, user_id):
        raise _forbidden()

    try:
        _service.delete_recipe(recipe_id=recipe_id, owner_id=user_id, db=db)
    except HTTPException:
        raise
    except PermissionError:
        raise _forbidden()
    except Exception:
        logger.exception("Failed to delete recipe_id=%s", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "Unable to delete recipe."},
        )
    return None


@router.post("/{recipe_id}/image", status_code=status.HTTP_201_CREATED)
def upload_recipe_image(
    recipe_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    existing = _service.get_recipe(recipe_id=recipe_id, db=db)
    if existing is None:
        raise _not_found(recipe_id)
    if not verify_ownership(existing.owner_id, user_id):
        raise _forbidden()

    try:
        image_url = _service.upload_image(file=file, recipe_id=recipe_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to upload image for recipe_id=%s", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "Unable to upload image."},
        )
    return {"recipe_id": recipe_id, "image_url": image_url}


@router.get("/{recipe_id}/image")
def get_recipe_image(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = _service.get_recipe(recipe_id=recipe_id, db=db)
    if existing is None:
        raise _not_found(recipe_id)

    image_url = _service.get_image_url(recipe_id=recipe_id)
    if image_url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"No image found for recipe '{recipe_id}'."},
        )
    return RedirectResponse(url=image_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
