"""Web UI router: recipe form and dashboard pages (server-rendered)."""
from datetime import datetime, timezone

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
        "recipe_id": None,
    }


def _recipe_context(recipe) -> dict:
    ctx = _empty_context()
    ctx["name"] = recipe.name
    ctx["ingredients"] = recipe.ingredients
    ctx["recipe_id"] = recipe.id
    return ctx


@router.get("/recipe")
def new_recipe_form(request: Request):
    ctx = _empty_context()
    return templates.TemplateResponse(request, "recipe-id.html", ctx)


@router.get("/recipe/new")
def new_recipe_form_alias(request: Request):
    ctx = _empty_context()
    return templates.TemplateResponse(request, "recipe-id.html", ctx)


@router.post("/recipe/save")
def save_new_recipe(
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create a new recipe (form has no id yet, so it posts here)."""
    service = RecipeService(db)
    try:
        new_id = service.create(RecipeCreateDTO(name=name, ingredients=ingredients))
    except ValidationError as exc:
        ctx = _empty_context()
        ctx["name"] = name
        ctx["ingredients"] = ingredients
        ctx["field_errors"] = _extract_field_errors(exc)
        return templates.TemplateResponse(
            request, "recipe-id.html", ctx, status_code=422
        )

    recipe = service.get_by_id(new_id)
    ctx = _recipe_context(recipe)
    ctx["success_message"] = "Recipe saved successfully."
    return templates.TemplateResponse(request, "recipe-id.html", ctx)


@router.get("/recipe/{recipe_id}")
def edit_recipe_form(request: Request, recipe_id: str, db: Session = Depends(get_db)):
    service = RecipeService(db)
    try:
        rid = int(recipe_id)
    except ValueError:
        return RedirectResponse(
            url=f"/?message=Recipe not found: {recipe_id}", status_code=303
        )

    try:
        recipe = service.get_by_id(rid)
    except RecipeNotFoundError:
        return RedirectResponse(
            url=f"/?message=Recipe not found: {rid}", status_code=303
        )

    ctx = _recipe_context(recipe)
    return templates.TemplateResponse(request, "recipe-id.html", ctx)


@router.post("/recipe/{recipe_id}")
def update_recipe(
    request: Request,
    recipe_id: str,
    name: str = Form(...),
    ingredients: str = Form(...),
    db: Session = Depends(get_db),
):
    service = RecipeService(db)

    try:
        rid = int(recipe_id)
    except ValueError:
        return RedirectResponse(
            url=f"/?message=Recipe not found: {recipe_id}", status_code=303
        )

    try:
        service.update(rid, RecipeUpdateDTO(name=name, ingredients=ingredients))
    except RecipeNotFoundError:
        return RedirectResponse(
            url=f"/?message=Recipe not found: {rid}", status_code=303
        )
    except ValidationError as exc:
        ctx = _empty_context()
        ctx["name"] = name
        ctx["ingredients"] = ingredients
        ctx["recipe_id"] = rid
        ctx["field_errors"] = _extract_field_errors(exc)
        return templates.TemplateResponse(
            request, "recipe-id.html", ctx, status_code=422
        )

    recipe = service.get_by_id(rid)
    ctx = _recipe_context(recipe)
    ctx["success_message"] = "Recipe saved successfully."
    return templates.TemplateResponse(request, "recipe-id.html", ctx)


def _extract_field_errors(exc: ValidationError) -> dict:
    """Normalize a ValidationError into a dict keyed by form field name."""
    errors = getattr(exc, "field_errors", None)
    if isinstance(errors, dict) and errors:
        return errors

    message = str(exc)
    lower = message.lower()
    if "ingredient" in lower:
        return {"ingredients": message}
    if "name" in lower:
        return {"name": message}
    return {"name": message, "ingredients": message}


@router.get("/dashboard")
def dashboard(request: Request, message: str = "", db: Session = Depends(get_db)):
    service = RecipeService(db)
    recipes = service.list_all()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "recipes": recipes,
            "error_message": message,
            "success_message": "",
        },
    )


@router.get("/")
def index():
    """Site root — the approved screens define no "/" page, so start at the first one."""
    return RedirectResponse(url="/recipe/{id}", status_code=303)
