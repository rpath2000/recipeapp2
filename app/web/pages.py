"""Web routes for the Recipe dashboard and form pages.

Renders the approved, pre-existing Jinja2 templates (index.html and
recipe-id.html) with data pulled in-process from RecipeService. No
template files are created or modified here.
"""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette import status

from app.contracts import (
    RecipeCreateDTO,
    RecipeNotFoundError,
    RecipeUpdateDTO,
    ValidationError,
)
from app.models import get_db
from app.services.recipe_service import RecipeService

router = APIRouter()

templates = Jinja2Templates(directory="app/web/templates")

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _sanitize(value: str) -> str:
    """Strip control characters except \\n and \\t, preserving everything else."""
    if value is None:
        return value
    return _CONTROL_CHAR_RE.sub("", value)


def _base_context(
    request: Request,
    recipe_id,
    name: str,
    ingredients: str,
    success_message: str = "",
    error_message: str = "",
    field_errors: dict | None = None,
) -> dict:
    return {
        "recipe_id": recipe_id,
        "name": name,
        "ingredients": ingredients,
        "success_message": success_message,
        "error_message": error_message,
        "field_errors": field_errors or {},
    }


@router.get("/recipe/new")
def new_recipe_form(request: Request):
    """Blank recipe form for creating a new recipe."""
    context = _base_context(
        request,
        recipe_id="new",
        name="",
        ingredients="",
    )
    return templates.TemplateResponse(request, "recipe-id.html", context)


@router.get("/recipe/{recipe_id}")
def edit_recipe_form(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    """Pre-populated recipe form, or redirect to dashboard if not found/malformed."""
    if recipe_id == "new":
        return new_recipe_form(request)

    try:
        numeric_id = int(recipe_id)
    except ValueError:
        return RedirectResponse(
            url=f"/?error_message=Recipe not found: {recipe_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    service = RecipeService(db)
    try:
        recipe = service.get_by_id(numeric_id)
    except RecipeNotFoundError:
        return RedirectResponse(
            url=f"/?error_message=Recipe not found: {numeric_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    context = _base_context(
        request,
        recipe_id=recipe.id,
        name=recipe.name,
        ingredients=recipe.ingredients,
    )
    return templates.TemplateResponse(request, "recipe-id.html", context)


@router.post("/recipe/save")
def save_recipe_new(
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create a brand-new recipe (form posts here without an id)."""
    return _save(request, recipe_id=None, name=name, ingredients=ingredients, db=db)


@router.post("/recipe/{recipe_id}")
def save_recipe(
    request: Request,
    recipe_id: str,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create or update a recipe depending on whether recipe_id is 'new' or numeric."""
    if recipe_id == "new":
        return _save(request, recipe_id=None, name=name, ingredients=ingredients, db=db)

    try:
        numeric_id = int(recipe_id)
    except ValueError:
        return RedirectResponse(
            url=f"/?error_message=Recipe not found: {recipe_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return _save(request, recipe_id=numeric_id, name=name, ingredients=ingredients, db=db)


def _save(request: Request, recipe_id, name: str, ingredients: str, db: Session):
    clean_name = _sanitize(name)
    clean_ingredients = _sanitize(ingredients)

    service = RecipeService(db)

    try:
        if recipe_id is None:
            new_id = service.create(
                RecipeCreateDTO(name=clean_name, ingredients=clean_ingredients)
            )
            recipe = service.get_by_id(new_id)
        else:
            service.update(
                recipe_id,
                RecipeUpdateDTO(name=clean_name, ingredients=clean_ingredients),
            )
            recipe = service.get_by_id(recipe_id)

        context = _base_context(
            request,
            recipe_id=recipe.id,
            name=recipe.name,
            ingredients=recipe.ingredients,
            success_message="Recipe saved successfully.",
        )
        return templates.TemplateResponse(request, "recipe-id.html", context)

    except ValidationError as exc:
        field_errors: dict = {}
        message = str(exc)
        lowered = message.lower()

        if "name" in lowered and "ingredient" not in lowered:
            field_errors["name"] = (
                "Recipe name is required and must not exceed 120 characters."
            )
        elif "ingredient" in lowered and "name" not in lowered:
            field_errors["ingredients"] = (
                "Ingredients are required and must not exceed 4000 characters."
            )
        else:
            if not clean_name or not clean_name.strip() or len(clean_name) > 120:
                field_errors["name"] = (
                    "Recipe name is required and must not exceed 120 characters."
                )
            if (
                not clean_ingredients
                or not clean_ingredients.strip()
                or len(clean_ingredients) > 4000
            ):
                field_errors["ingredients"] = (
                    "Ingredients are required and must not exceed 4000 characters."
                )
            if not field_errors:
                field_errors["name"] = message

        display_recipe_id = recipe_id if recipe_id is not None else "new"
        context = _base_context(
            request,
            recipe_id=display_recipe_id,
            name=name,
            ingredients=ingredients,
            field_errors=field_errors,
        )
        return templates.TemplateResponse(
            request,
            "recipe-id.html",
            context,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    except RecipeNotFoundError:
        return RedirectResponse(
            url=f"/?error_message=Recipe not found: {recipe_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/")
def index():
    """Site root — the approved screens define no "/" page, so start at the first one."""
    return RedirectResponse(url="/recipe/{id}", status_code=303)
