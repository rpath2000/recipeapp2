"""
Server-rendered web UI for the Recipe application.

Serves the approved (already on disk) Jinja2 templates:
  - GET  /               -> templates/index.html      (Dashboard)
  - GET  /recipe/new     -> templates/recipe-id.html   (blank form)
  - GET  /recipe/{id}    -> templates/recipe-id.html   (pre-populated form)
  - POST /recipe/save    -> handles Save from recipe-id.html
  - POST /recipe/{id}    -> handles Save when action targets an explicit id

All database access goes through app.services.recipe_service.RecipeService,
constructed per-request with a session obtained from app.models.get_db.
Shared DTOs and exceptions come from app.contracts.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

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
async def dashboard(request: Request, db: Session = Depends(get_db)):
    service = RecipeService(db)
    recipes = service.list_all()
    recipes_sorted = sorted(
        recipes, key=lambda r: (r.updated_at, r.id), reverse=True
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "recipes": recipes_sorted,
            "success_message": request.query_params.get("success_message", ""),
            "error_message": request.query_params.get("error_message", ""),
        },
    )


@router.get("/recipe/new")
async def new_recipe_form(request: Request):
    return templates.TemplateResponse(
        request,
        "recipe-id.html",
        {
            "recipe_id": None,
            "name": "",
            "ingredients": "",
            "success_message": "",
            "error_message": "",
            "field_errors": _empty_field_errors(),
        },
    )


@router.get("/recipe/{recipe_id}")
async def edit_recipe_form(
    recipe_id: str, request: Request, db: Session = Depends(get_db)
):
    service = RecipeService(db)
    try:
        parsed_id = int(recipe_id)
    except (TypeError, ValueError):
        return RedirectResponse(
            url=f"/?error_message=Recipe not found: {recipe_id}",
            status_code=303,
        )

    try:
        recipe = service.get_by_id(parsed_id)
    except RecipeNotFoundError:
        return RedirectResponse(
            url=f"/?error_message=Recipe not found: {recipe_id}",
            status_code=303,
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


def _render_form_response(
    request: Request,
    recipe_id,
    name: str,
    ingredients: str,
    success_message: str = "",
    error_message: str = "",
    field_errors: dict | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "recipe-id.html",
        {
            "recipe_id": recipe_id,
            "name": name,
            "ingredients": ingredients,
            "success_message": success_message,
            "error_message": error_message,
            "field_errors": field_errors or _empty_field_errors(),
        },
        status_code=status_code,
    )


async def _save_recipe(
    request: Request,
    recipe_id: str,
    name: str,
    ingredients: str,
    db: Session,
):
    service = RecipeService(db)

    parsed_id = None
    if recipe_id not in (None, "", "new"):
        try:
            parsed_id = int(recipe_id)
        except (TypeError, ValueError):
            return RedirectResponse(
                url=f"/?error_message=Recipe not found: {recipe_id}",
                status_code=303,
            )

    try:
        if parsed_id is None:
            new_id = service.create(RecipeCreateDTO(name=name, ingredients=ingredients))
            saved = service.get_by_id(new_id)
        else:
            service.update(parsed_id, RecipeUpdateDTO(name=name, ingredients=ingredients))
            saved = service.get_by_id(parsed_id)
    except ValidationError as exc:
        field_errors = _empty_field_errors()
        details = getattr(exc, "errors", None)
        if isinstance(details, dict):
            for key in field_errors:
                if key in details:
                    field_errors[key] = str(details[key])
        else:
            message = str(exc)
            if "name" in message.lower():
                field_errors["name"] = message
            elif "ingredient" in message.lower():
                field_errors["ingredients"] = message
            else:
                field_errors["name"] = message
        return _render_form_response(
            request,
            recipe_id=parsed_id,
            name=name,
            ingredients=ingredients,
            field_errors=field_errors,
            status_code=422,
        )
    except RecipeNotFoundError:
        return RedirectResponse(
            url=f"/?error_message=Recipe not found: {recipe_id}",
            status_code=303,
        )

    return _render_form_response(
        request,
        recipe_id=saved.id,
        name=saved.name,
        ingredients=saved.ingredients,
        success_message="Recipe saved successfully.",
        status_code=200,
    )


@router.post("/recipe/save")
async def save_recipe_no_id(
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    return await _save_recipe(request, "new", name, ingredients, db)


@router.post("/recipe/{recipe_id}")
async def save_recipe_with_id(
    recipe_id: str,
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    return await _save_recipe(request, recipe_id, name, ingredients, db)
