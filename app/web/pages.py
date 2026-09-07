"""Server-rendered web UI for the Recipe application.

Implements FastAPI routes that render the pre-approved Jinja2 templates
(templates/index.html and templates/recipe-id.html) using data retrieved
in-process from RecipeService. No JSON API, no SPA, no static assets.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

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


def _empty_field_errors() -> dict:
    return {"name": "", "ingredients": ""}


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Render the recipe dashboard with all recipes ordered per US-009."""
    service = RecipeService(db)
    recipes = service.list_all()

    not_found_message = request.query_params.get("not_found_message", "")

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "recipes": recipes,
            "success_message": "",
            "error_message": not_found_message,
            "field_errors": _empty_field_errors(),
        },
    )


@router.get("/recipe/new")
def new_recipe_form(request: Request):
    """Render a blank recipe form for creating a new record."""
    return templates.TemplateResponse(
        request,
        "recipe-id.html",
        {
            "recipe_id": "new",
            "name": "",
            "ingredients": "",
            "success_message": "",
            "error_message": "",
            "field_errors": _empty_field_errors(),
        },
    )


@router.get("/recipe/{recipe_id}")
def edit_recipe_form(recipe_id: str, request: Request, db: Session = Depends(get_db)):
    """Render the recipe form pre-populated with an existing recipe.

    Redirects to the dashboard with a not-found message when the id is
    malformed or does not correspond to an existing recipe, per FRS-017.
    """
    try:
        numeric_id = int(recipe_id)
    except (TypeError, ValueError):
        message = f"Recipe not found: {recipe_id}"
        return RedirectResponse(
            url=f"/?not_found_message={message}", status_code=303
        )

    service = RecipeService(db)
    try:
        recipe = service.get_by_id(numeric_id)
    except RecipeNotFoundError:
        message = f"Recipe not found: {numeric_id}"
        return RedirectResponse(
            url=f"/?not_found_message={message}", status_code=303
        )

    return templates.TemplateResponse(
        request,
        "recipe-id.html",
        {
            "recipe_id": recipe.id,
            "name": recipe.name,
            "ingredients": recipe.ingredients,
            "success_message": "",
            "error_message": "",
            "field_errors": _empty_field_errors(),
        },
    )


def _save_recipe(
    recipe_id: str,
    request: Request,
    name: str,
    ingredients: str,
    db: Session,
):
    """Shared logic for creating/updating a recipe from posted form fields."""
    service = RecipeService(db)

    is_new = recipe_id in ("new", "") or recipe_id is None

    if is_new:
        try:
            new_id = service.create(RecipeCreateDTO(name=name, ingredients=ingredients))
        except ValidationError as exc:
            field_errors = _empty_field_errors()
            field_errors.update(getattr(exc, "field_errors", {}) or {})
            return templates.TemplateResponse(
                request,
                "recipe-id.html",
                {
                    "recipe_id": "new",
                    "name": name,
                    "ingredients": ingredients,
                    "success_message": "",
                    "error_message": "",
                    "field_errors": field_errors,
                },
                status_code=422,
            )

        saved = service.get_by_id(new_id)
        return templates.TemplateResponse(
            request,
            "recipe-id.html",
            {
                "recipe_id": saved.id,
                "name": saved.name,
                "ingredients": saved.ingredients,
                "success_message": "Recipe saved successfully.",
                "error_message": "",
                "field_errors": _empty_field_errors(),
            },
            status_code=200,
        )

    try:
        numeric_id = int(recipe_id)
    except (TypeError, ValueError):
        message = f"Recipe not found: {recipe_id}"
        return RedirectResponse(
            url=f"/?not_found_message={message}", status_code=303
        )

    try:
        service.update(numeric_id, RecipeUpdateDTO(name=name, ingredients=ingredients))
    except RecipeNotFoundError:
        message = f"Recipe not found: {numeric_id}"
        return RedirectResponse(
            url=f"/?not_found_message={message}", status_code=303
        )
    except ValidationError as exc:
        field_errors = _empty_field_errors()
        field_errors.update(getattr(exc, "field_errors", {}) or {})
        return templates.TemplateResponse(
            request,
            "recipe-id.html",
            {
                "recipe_id": numeric_id,
                "name": name,
                "ingredients": ingredients,
                "success_message": "",
                "error_message": "",
                "field_errors": field_errors,
            },
            status_code=422,
        )

    saved = service.get_by_id(numeric_id)
    return templates.TemplateResponse(
        request,
        "recipe-id.html",
        {
            "recipe_id": saved.id,
            "name": saved.name,
            "ingredients": saved.ingredients,
            "success_message": "Recipe saved successfully.",
            "error_message": "",
            "field_errors": _empty_field_errors(),
        },
        status_code=200,
    )


@router.post("/recipe/save")
def save_recipe_generic(
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle the approved form's POST target of /recipe/save.

    The approved markup posts to /recipe/save without an id in the path;
    the record being edited is identified by a hidden/query recipe_id
    value carried from the page that rendered the form. Falls back to
    creating a new recipe when no id is present.
    """
    recipe_id = request.query_params.get("recipe_id") or "new"
    return _save_recipe(recipe_id, request, name, ingredients, db)


@router.post("/recipe/{recipe_id}")
def save_recipe(
    recipe_id: str,
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle POST /recipe/{id} submissions per US-013/US-014.

    On success: persists the record, returns 200 with the form
    repopulated and a success message. On validation failure: returns
    422 with the form retaining typed values and field-specific errors.
    On not-found (existing id path only): redirects to the dashboard.
    """
    return _save_recipe(recipe_id, request, name, ingredients, db)
