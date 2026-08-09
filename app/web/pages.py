"""
Server-rendered recipe UI router.

Renders the approved (already on-disk) Jinja2 templates and wires them to
the in-process RecipeService via app.contracts DTOs. All forms POST back to
routes in this module which call the service directly (no HTTP self-calls).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.contracts import RecipeCreateIn, RecipeUpdateIn
from app.models.database import get_db
from app.services.recipe_service import RecipeService
from app.security.sso_middleware import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

_service = RecipeService()

DEFAULT_PAGE_SIZE = 10

CATEGORIES = [
    "Breakfast & Brunch",
    "Lunch & Midday",
    "Appetizers & Snacks",
    "Soups & Stews",
    "Main Dishes / Entrees",
    "Side Dishes",
    "Desserts",
]


def _empty_recipe() -> dict:
    """Shape used by the new/create form when no recipe exists yet."""
    return {
        "id": None,
        "name": "",
        "description": "",
        "ingredients": "",
        "instructions": "",
        "category": "",
        "image_url": None,
        "created_at": None,
        "updated_at": None,
        "owner_id": None,
        "errors": {},
        "categories": CATEGORIES,
    }


def _recipe_to_dict(recipe, errors: Optional[dict] = None) -> dict:
    if recipe is None:
        d = _empty_recipe()
        if errors:
            d["errors"] = errors
        return d
    return {
        "id": recipe.id,
        "name": recipe.name,
        "description": recipe.description,
        "ingredients": recipe.ingredients,
        "instructions": recipe.instructions,
        "category": recipe.category,
        "image_url": recipe.image_url,
        "created_at": recipe.created_at,
        "updated_at": recipe.updated_at,
        "owner_id": recipe.owner_id,
        "errors": errors or {},
        "categories": CATEGORIES,
    }


def _validate_form(name: str, description: str, ingredients: str,
                    instructions: str, category: str) -> dict:
    errors: dict = {}
    if not name or not name.strip():
        errors["name"] = "Recipe Name is required"
    if not description or not description.strip():
        errors["description"] = "Description is required"
    if not ingredients or not ingredients.strip():
        errors["ingredients"] = "Ingredients are required"
    if not instructions or not instructions.strip():
        errors["instructions"] = "Instructions are required"
    if not category or not category.strip():
        errors["category"] = "Category is required"
    return errors


# ---------------------------------------------------------------------------
# Recipe list
# ---------------------------------------------------------------------------

@router.get("/recipes")
def list_recipes(
    request: Request,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    q: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    if q:
        result = _service.search_recipes(q, page, page_size, db)
    elif category:
        result = _service.filter_recipes_by_category(category, page, page_size, db)
    else:
        result = _service.list_recipes(page, page_size, db)

    return templates.TemplateResponse(
        request,
        "recipes.html",
        {
            "recipes": [r.__dict__ if hasattr(r, "__dict__") else r for r in result.items],
            "items": result.items,
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "total_pages": result.total_pages,
            "query": q or "",
            "category": category or "",
            "categories": CATEGORIES,
        },
    )


# ---------------------------------------------------------------------------
# Search page (also used by HTMX search bar / JS fetch)
# ---------------------------------------------------------------------------

@router.get("/recipes/search")
def search_recipes(
    request: Request,
    q: Optional[str] = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    if category:
        result = _service.filter_recipes_by_category(category, page, page_size, db)
    elif q:
        result = _service.search_recipes(q, page, page_size, db)
    else:
        result = _service.list_recipes(page, page_size, db)

    return templates.TemplateResponse(
        request,
        "recipes-search.html",
        {
            "recipes": result.items,
            "items": result.items,
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "total_pages": result.total_pages,
            "query": q or "",
            "category": category or "",
            "categories": CATEGORIES,
            "no_results": result.total == 0,
        },
    )


# ---------------------------------------------------------------------------
# New recipe form (GET) + custom category variant
# ---------------------------------------------------------------------------

@router.get("/recipes/new")
def new_recipe_form(request: Request):
    return templates.TemplateResponse(
        request,
        "recipes-new.html",
        {"recipe": _empty_recipe()},
    )


@router.get("/recipes/new-custom-category")
def new_recipe_custom_category_form(request: Request):
    return templates.TemplateResponse(
        request,
        "recipes-new-custom-category.html",
        {"recipe": _empty_recipe()},
    )


@router.post("/recipes/new")
async def create_recipe(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    ingredients: str = Form(""),
    instructions: str = Form(""),
    category: str = Form(""),
    custom_category: str = Form(""),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    effective_category = (custom_category or category or "").strip() or category

    errors = _validate_form(name, description, ingredients, instructions, effective_category)

    if errors:
        stub = {
            "id": None,
            "name": name,
            "description": description,
            "ingredients": ingredients,
            "instructions": instructions,
            "category": effective_category,
            "image_url": None,
            "created_at": None,
            "updated_at": None,
            "owner_id": None,
            "errors": errors,
            "categories": CATEGORIES,
        }
        return templates.TemplateResponse(
            request,
            "recipes-new.html",
            {"recipe": stub},
            status_code=422,
        )

    owner_id = get_current_user(request)

    image_url = None
    if image is not None and getattr(image, "filename", None):
        try:
            image_url = _service.upload_image(image, "pending")
        except Exception:
            logger.exception("Image upload failed during recipe creation")
            image_url = None

    recipe_in = RecipeCreateIn(
        name=name.strip(),
        description=description.strip(),
        ingredients=ingredients.strip(),
        instructions=instructions.strip(),
        category=effective_category.strip(),
        image_url=image_url,
    )

    created = _service.create_recipe(recipe_in, owner_id, db)

    if image is not None and getattr(image, "filename", None) and image_url is None:
        try:
            new_url = _service.upload_image(image, created.id)
            if new_url:
                update_in = RecipeUpdateIn(
                    name=created.name,
                    description=created.description,
                    ingredients=created.ingredients,
                    instructions=created.instructions,
                    category=created.category,
                    image_url=new_url,
                )
                created = _service.update_recipe(created.id, update_in, owner_id, db)
        except Exception:
            logger.exception("Post-create image association failed")

    return RedirectResponse(url=f"/recipes/{created.id}", status_code=303)


# ---------------------------------------------------------------------------
# Recipe detail
# ---------------------------------------------------------------------------

@router.get("/recipes/{recipe_id}")
def recipe_detail(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    recipe = _service.get_recipe(recipe_id, db)
    current_user = get_current_user(request)

    if recipe is None:
        return templates.TemplateResponse(
            request,
            "recipes-id.html",
            {"recipe": {**_empty_recipe(), "id": recipe_id, "not_found": True}},
            status_code=404,
        )

    is_owner = recipe.owner_id == current_user

    return templates.TemplateResponse(
        request,
        "recipes-id.html",
        {
            "recipe": {
                "id": recipe.id,
                "name": recipe.name,
                "description": recipe.description,
                "ingredients": recipe.ingredients,
                "instructions": recipe.instructions,
                "category": recipe.category,
                "image_url": recipe.image_url,
                "created_at": recipe.created_at,
                "updated_at": recipe.updated_at,
                "owner_id": recipe.owner_id,
                "is_owner": is_owner,
                "not_found": False,
            }
        },
    )


# ---------------------------------------------------------------------------
# Edit recipe (two approved templates map to the same edit flow)
# ---------------------------------------------------------------------------

def _load_recipe_for_edit(request: Request, recipe_id: str, db: Session):
    recipe = _service.get_recipe(recipe_id, db)
    current_user = get_current_user(request)
    if recipe is None:
        return None, current_user, False
    is_owner = recipe.owner_id == current_user
    return recipe, current_user, is_owner


@router.get("/recipes/{recipe_id}/edit")
def edit_recipe_form(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    recipe, current_user, is_owner = _load_recipe_for_edit(request, recipe_id, db)

    if recipe is None:
        return templates.TemplateResponse(
            request,
            "recipes-id-edit.html",
            {"recipe": {**_empty_recipe(), "id": recipe_id, "not_found": True}},
            status_code=404,
        )

    if not is_owner:
        return templates.TemplateResponse(
            request,
            "recipes-id-edit.html",
            {
                "recipe": {
                    **_recipe_to_dict(recipe),
                    "forbidden": True,
                }
            },
            status_code=403,
        )

    recipe_dict = _recipe_to_dict(recipe)
    recipe_dict["is_owner"] = True
    recipe_dict["forbidden"] = False
    recipe_dict["not_found"] = False

    return templates.TemplateResponse(
        request,
        "recipes-id-edit.html",
        {"recipe": recipe_dict},
    )


@router.get("/recipes/{recipe_id}/edit-form")
def edit_recipe_form_v2(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    """Serves recipes-id-edit-2.html (the alternate approved edit form)."""
    recipe, current_user, is_owner = _load_recipe_for_edit(request, recipe_id, db)

    if recipe is None:
        return templates.TemplateResponse(
            request,
            "recipes-id-edit-2.html",
            {"recipe": {**_empty_recipe(), "id": recipe_id, "not_found": True}},
            status_code=404,
        )

    if not is_owner:
        return templates.TemplateResponse(
            request,
            "recipes-id-edit-2.html",
            {"recipe": {**_recipe_to_dict(recipe), "forbidden": True}},
            status_code=403,
        )

    recipe_dict = _recipe_to_dict(recipe)
    recipe_dict["is_owner"] = True
    recipe_dict["forbidden"] = False
    recipe_dict["not_found"] = False

    return templates.TemplateResponse(
        request,
        "recipes-id-edit-2.html",
        {"recipe": recipe_dict},
    )


@router.post("/recipes/{recipe_id}/edit")
async def update_recipe(
    request: Request,
    recipe_id: str,
    name: str = Form(""),
    description: str = Form(""),
    ingredients: str = Form(""),
    instructions: str = Form(""),
    category: str = Form(""),
    custom_category: str = Form(""),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    existing = _service.get_recipe(recipe_id, db)
    current_user = get_current_user(request)

    if existing is None:
        return templates.TemplateResponse(
            request,
            "recipes-id-edit.html",
            {"recipe": {**_empty_recipe(), "id": recipe_id, "not_found": True}},
            status_code=404,
        )

    if existing.owner_id != current_user:
        return templates.TemplateResponse(
            request,
            "recipes-id-edit.html",
            {"recipe": {**_recipe_to_dict(existing), "forbidden": True}},
            status_code=403,
        )

    effective_category = (custom_category or category or "").strip() or category
    errors = _validate_form(name, description, ingredients, instructions, effective_category)

    if errors:
        stub = _recipe_to_dict(existing, errors=errors)
        stub["name"] = name
        stub["description"] = description
        stub["ingredients"] = ingredients
        stub["instructions"] = instructions
        stub["category"] = effective_category
        stub["is_owner"] = True
        stub["forbidden"] = False
        stub["not_found"] = False
        return templates.TemplateResponse(
            request,
            "recipes-id-edit.html",
            {"recipe": stub},
            status_code=422,
        )

    image_url = existing.image_url
    if image is not None and getattr(image, "filename", None):
        try:
            new_url = _service.upload_image(image, recipe_id)
            if new_url:
                image_url = new_url
        except Exception:
            logger.exception("Image upload failed during recipe update")

    recipe_in = RecipeUpdateIn(
        name=name.strip(),
        description=description.strip(),
        ingredients=ingredients.strip(),
        instructions=instructions.strip(),
        category=effective_category.strip(),
        image_url=image_url,
    )

    updated = _service.update_recipe(recipe_id, recipe_in, current_user, db)
    return RedirectResponse(url=f"/recipes/{updated.id}", status_code=303)


# ---------------------------------------------------------------------------
# Delete confirmation dialogs
# ---------------------------------------------------------------------------

@router.get("/recipes/delete-confirm")
def delete_confirm_generic(request: Request, recipe_id: Optional[str] = None, db: Session = Depends(get_db)):
    recipe = _service.get_recipe(recipe_id, db) if recipe_id else None
    current_user = get_current_user(request)
    recipe_dict = _recipe_to_dict(recipe) if recipe else {**_empty_recipe(), "id": recipe_id}
    return templates.TemplateResponse(
        request,
        "recipes-delete-confirm.html",
        {"recipe": recipe_dict, "user": current_user},
    )


@router.get("/recipes/{recipe_id}/delete-confirm")
def delete_confirm(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    recipe = _service.get_recipe(recipe_id, db)
    current_user = get_current_user(request)

    if recipe is None:
        return templates.TemplateResponse(
            request,
            "recipes-id-delete-confirm.html",
            {"recipe": {**_empty_recipe(), "id": recipe_id, "not_found": True}, "user": current_user},
            status_code=404,
        )

    recipe_dict = _recipe_to_dict(recipe)
    recipe_dict["is_owner"] = recipe.owner_id == current_user
    recipe_dict["not_found"] = False

    return templates.TemplateResponse(
        request,
        "recipes-id-delete-confirm.html",
        {"recipe": recipe_dict, "user": current_user},
    )


@router.post("/recipes/{recipe_id}/delete")
async def delete_recipe(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request)
    existing = _service.get_recipe(recipe_id, db)

    if existing is None:
        return RedirectResponse(url="/recipes", status_code=303)

    if existing.owner_id != current_user:
        return templates.TemplateResponse(
            request,
            "recipes-id-delete-confirm.html",
            {
                "recipe": {**_recipe_to_dict(existing), "forbidden": True},
                "user": current_user,
            },
            status_code=403,
        )

    _service.delete_recipe(recipe_id, current_user, db)
    return RedirectResponse(url="/recipes", status_code=303)


# ---------------------------------------------------------------------------
# Admin dashboards (static approved markup, no dynamic context required)
# ---------------------------------------------------------------------------

@router.get("/admin/system-health")
def system_health(request: Request):
    return templates.TemplateResponse(request, "admin-system-health.html", {})


@router.get("/admin/performance")
def performance_dashboard(request: Request):
    return templates.TemplateResponse(request, "admin-performance.html", {})


@router.get("/")
def index():
    """Site root — the approved screens define no "/" page, so start at the first one."""
    return RedirectResponse(url="/recipes/new", status_code=303)
