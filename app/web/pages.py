from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.contracts import ValidationError
from app.integrations.templates import templates
from app.models import get_db
from app.services.recipe import RecipeService

router = APIRouter()


def _empty_context() -> dict:
    return {
        "success_message": "",
        "field_errors": {},
        "error_message": "",
        "recipe_name": "",
        "recipe_ingredients": "",
    }


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    service = RecipeService()
    recipes = service.list_recipes(db)
    recipes_sorted = sorted(
        recipes, key=lambda r: (r.updated_at, r.id), reverse=True
    )
    context = {
        "recipes": recipes_sorted,
    }
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/recipe")
def recipe_form(request: Request, id: int | None = None, saved: int | None = None, db: Session = Depends(get_db)):
    service = RecipeService()
    context = _empty_context()
    recipe = None
    if id is not None:
        recipe = service.get_recipe(id, db)

    if recipe is not None:
        context["recipe_id"] = recipe.id
        context["recipe_name"] = recipe.name
        context["recipe_ingredients"] = recipe.ingredients
    else:
        context["recipe_id"] = None

    if saved and recipe is not None:
        context["success_message"] = "Recipe saved successfully"

    return templates.TemplateResponse(request, "recipe.html", context)


@router.post("/recipe")
def save_recipe(
    request: Request,
    recipe_name: Annotated[str, Form(alias="recipe-name")] = "",
    recipe_ingredients: Annotated[str, Form(alias="recipe-ingredients")] = "",
    id: int | None = None,
    db: Session = Depends(get_db),
):
    service = RecipeService()

    existing_id: int | None = id
    if existing_id is None:
        raw_id = request.query_params.get("id")
        if raw_id is not None:
            try:
                existing_id = int(raw_id)
            except ValueError:
                existing_id = None

    try:
        if existing_id is not None and service.get_recipe(existing_id, db) is not None:
            recipe = service.update_recipe(existing_id, recipe_name, recipe_ingredients, db)
        else:
            recipe = service.create_recipe(recipe_name, recipe_ingredients, db)
    except ValidationError as exc:
        context = _empty_context()
        context["recipe_name"] = recipe_name
        context["recipe_ingredients"] = recipe_ingredients
        context["recipe_id"] = existing_id

        field_errors: dict[str, str] = {}
        details = getattr(exc, "errors", None)
        if isinstance(details, dict):
            for field, message in details.items():
                if field in ("name", "recipe_name", "recipe-name"):
                    field_errors["recipe-name"] = message
                elif field in ("ingredients", "recipe_ingredients", "recipe-ingredients"):
                    field_errors["recipe-ingredients"] = message
                else:
                    field_errors[field] = message
        else:
            message = str(exc)
            lowered = message.lower()
            if "ingredient" in lowered:
                field_errors["recipe-ingredients"] = message
            elif "name" in lowered:
                field_errors["recipe-name"] = message
            else:
                context["error_message"] = message

        context["field_errors"] = field_errors
        return templates.TemplateResponse(request, "recipe.html", context, status_code=200)

    return RedirectResponse(
        url=f"/recipe?id={recipe.id}&saved=1", status_code=303
    )
