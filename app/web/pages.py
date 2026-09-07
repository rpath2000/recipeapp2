"""Server-rendered web UI routes for the Recipe application.

Renders the approved Jinja2 templates (index.html, recipe-id.html) and
handles form submissions by calling the RecipeService in-process.
"""
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


def _empty_context() -> dict:
    return {
        "success_message": "",
        "field_errors": {},
        "error_message": "",
        "name": "",
        "ingredients": "",
    }


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Render the recipe dashboard with all recipes ordered per US-009."""
    service = RecipeService(db)
    not_found_message = request.query_params.get("not_found_message", "")
    recipes = service.list_all()
    context = {
        "recipes": recipes,
        "success_message": "",
        "error_message": "",
        "not_found_message": not_found_message,
    }
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/recipe/new")
def new_recipe_form(request: Request):
    """Render a blank recipe form for creating a new recipe."""
    context = _empty_context()
    return templates.TemplateResponse(request, "recipe-id.html", context)


@router.get("/recipe/{recipe_id}")
def recipe_form(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    """Render the recipe form, pre-populated when the id is a valid existing recipe."""
    if recipe_id == "new":
        context = _empty_context()
        return templates.TemplateResponse(request, "recipe-id.html", context)

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
        message = f"Recipe not found: {recipe_id}"
        return RedirectResponse(
            url=f"/?not_found_message={message}", status_code=303
        )

    context = {
        "success_message": "",
        "field_errors": {},
        "error_message": "",
        "name": recipe.name,
        "ingredients": recipe.ingredients,
        "recipe_id": recipe.id,
    }
    return templates.TemplateResponse(request, "recipe-id.html", context)


@router.post("/recipe/save")
def create_recipe(
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create a new recipe (form posts here when no id is known yet)."""
    service = RecipeService(db)
    try:
        new_id = service.create(RecipeCreateDTO(name=name, ingredients=ingredients))
    except ValidationError as exc:
        context = {
            "success_message": "",
            "field_errors": exc.field_errors if hasattr(exc, "field_errors") else {"name": str(exc)},
            "error_message": "",
            "name": name,
            "ingredients": ingredients,
        }
        response = templates.TemplateResponse(request, "recipe-id.html", context)
        response.status_code = 422
        return response

    recipe = service.get_by_id(new_id)
    context = {
        "success_message": "Recipe saved successfully.",
        "field_errors": {},
        "error_message": "",
        "name": recipe.name,
        "ingredients": recipe.ingredients,
        "recipe_id": recipe.id,
    }
    return templates.TemplateResponse(request, "recipe-id.html", context)


@router.post("/recipe/{recipe_id}")
def save_recipe(
    request: Request,
    recipe_id: str,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle Save from the recipe form: create when id is 'new', else update."""
    service = RecipeService(db)

    if recipe_id == "new":
        try:
            new_id = service.create(RecipeCreateDTO(name=name, ingredients=ingredients))
        except ValidationError as exc:
            field_errors = getattr(exc, "field_errors", None) or {"name": str(exc)}
            context = {
                "success_message": "",
                "field_errors": field_errors,
                "error_message": "",
                "name": name,
                "ingredients": ingredients,
            }
            response = templates.TemplateResponse(request, "recipe-id.html", context)
            response.status_code = 422
            return response

        recipe = service.get_by_id(new_id)
        context = {
            "success_message": "Recipe saved successfully.",
            "field_errors": {},
            "error_message": "",
            "name": recipe.name,
            "ingredients": recipe.ingredients,
            "recipe_id": recipe.id,
        }
        return templates.TemplateResponse(request, "recipe-id.html", context)

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
        message = f"Recipe not found: {recipe_id}"
        return RedirectResponse(
            url=f"/?not_found_message={message}", status_code=303
        )
    except ValidationError as exc:
        field_errors = getattr(exc, "field_errors", None) or {"name": str(exc)}
        context = {
            "success_message": "",
            "field_errors": field_errors,
            "error_message": "",
            "name": name,
            "ingredients": ingredients,
            "recipe_id": numeric_id,
        }
        response = templates.TemplateResponse(request, "recipe-id.html", context)
        response.status_code = 422
        return response

    recipe = service.get_by_id(numeric_id)
    context = {
        "success_message": "Recipe saved successfully.",
        "field_errors": {},
        "error_message": "",
        "name": recipe.name,
        "ingredients": recipe.ingredients,
        "recipe_id": recipe.id,
    }
    return templates.TemplateResponse(request, "recipe-id.html", context)
