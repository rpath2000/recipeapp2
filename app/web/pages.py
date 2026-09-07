from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.status import HTTP_303_SEE_OTHER, HTTP_422_UNPROCESSABLE_ENTITY

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


def _base_context(
    name: str = "",
    ingredients: str = "",
    success_message: str = "",
    error_message: str = "",
    field_errors: dict | None = None,
) -> dict:
    return {
        "name": name,
        "ingredients": ingredients,
        "success_message": success_message,
        "error_message": error_message,
        "field_errors": field_errors or {},
    }


@router.get("/recipe")
def new_recipe_form(request: Request):
    context = _base_context()
    context["recipe"] = None
    return templates.TemplateResponse(request, "recipe-id.html", context)


@router.get("/recipe/{recipe_id}")
def edit_recipe_form(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    try:
        parsed_id = int(recipe_id)
    except (TypeError, ValueError):
        return RedirectResponse(
            url=f"/?message=Recipe not found: {recipe_id}",
            status_code=HTTP_303_SEE_OTHER,
        )

    service = RecipeService(db)
    try:
        recipe = service.get_by_id(parsed_id)
    except RecipeNotFoundError:
        return RedirectResponse(
            url=f"/?message=Recipe {parsed_id} was not found",
            status_code=HTTP_303_SEE_OTHER,
        )

    context = _base_context(name=recipe.name, ingredients=recipe.ingredients)
    context["recipe"] = recipe
    return templates.TemplateResponse(request, "recipe-id.html", context)


@router.post("/recipe/save")
def save_new_recipe(
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    return _do_save(request, None, name, ingredients, db)


@router.post("/recipe/{recipe_id}")
def save_recipe(
    request: Request,
    recipe_id: str,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    if recipe_id == "new":
        return _do_save(request, None, name, ingredients, db)

    try:
        parsed_id = int(recipe_id)
    except (TypeError, ValueError):
        return RedirectResponse(
            url=f"/?message=Recipe not found: {recipe_id}",
            status_code=HTTP_303_SEE_OTHER,
        )

    return _do_save(request, parsed_id, name, ingredients, db)


def _do_save(
    request: Request,
    recipe_id: int | None,
    name: str,
    ingredients: str,
    db: Session,
):
    service = RecipeService(db)

    if recipe_id is None:
        try:
            new_id = service.create(RecipeCreateDTO(name=name, ingredients=ingredients))
        except ValidationError as exc:
            context = _base_context(
                name=name,
                ingredients=ingredients,
                field_errors=_field_errors_from_exception(exc),
            )
            context["recipe"] = None
            return templates.TemplateResponse(
                request,
                "recipe-id.html",
                context,
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            )

        recipe = service.get_by_id(new_id)
        context = _base_context(
            name=recipe.name,
            ingredients=recipe.ingredients,
            success_message="Recipe saved successfully.",
        )
        context["recipe"] = recipe
        return templates.TemplateResponse(request, "recipe-id.html", context)

    try:
        service.update(recipe_id, RecipeUpdateDTO(name=name, ingredients=ingredients))
    except RecipeNotFoundError:
        return RedirectResponse(
            url=f"/?message=Recipe {recipe_id} was not found",
            status_code=HTTP_303_SEE_OTHER,
        )
    except ValidationError as exc:
        context = _base_context(
            name=name,
            ingredients=ingredients,
            field_errors=_field_errors_from_exception(exc),
        )
        context["recipe"] = None
        return templates.TemplateResponse(
            request,
            "recipe-id.html",
            context,
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        )

    recipe = service.get_by_id(recipe_id)
    context = _base_context(
        name=recipe.name,
        ingredients=recipe.ingredients,
        success_message="Recipe saved successfully.",
    )
    context["recipe"] = recipe
    return templates.TemplateResponse(request, "recipe-id.html", context)


def _field_errors_from_exception(exc: ValidationError) -> dict:
    errors = getattr(exc, "field_errors", None)
    if isinstance(errors, dict) and errors:
        return errors

    message = str(exc)
    lowered = message.lower()
    field_errors: dict = {}
    if "name" in lowered:
        field_errors["name"] = (
            "Recipe name is required and must not exceed 120 characters."
        )
    if "ingredient" in lowered:
        field_errors["ingredients"] = (
            "Ingredients are required and must not exceed 4000 characters."
        )

    if not field_errors:
        field_errors["name"] = message

    return field_errors


@router.get("/")
def index():
    """Site root — the approved screens define no "/" page, so start at the first one."""
    return RedirectResponse(url="/recipe/{id}", status_code=303)
