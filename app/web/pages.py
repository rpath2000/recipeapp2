from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.contracts import ValidationError
from app.models import get_db
from app.services import RecipeService

router = APIRouter()

templates = Jinja2Templates(directory="app/web/templates")


def _empty_context() -> dict:
    return {
        "success_message": "",
        "field_errors": {},
        "error_message": "",
        "recipe_name": "",
        "ingredients": "",
        "recipe_id": None,
    }


@router.get("/recipe")
async def recipe_form(request: Request, id: int | None = None, db: Session = Depends(get_db)):
    context = _empty_context()

    if id is not None:
        service = RecipeService(db)
        recipe = service.get_by_id(id)
        if recipe is not None:
            context["recipe_name"] = recipe.name
            context["ingredients"] = recipe.ingredients
            context["recipe_id"] = recipe.id

    return templates.TemplateResponse(request, "recipe.html", context)


@router.post("/recipe")
async def recipe_submit(
    request: Request,
    recipe_name: str = Form(""),
    ingredients: str = Form(""),
    id: int | None = None,
    db: Session = Depends(get_db),
):
    context = _empty_context()
    context["recipe_name"] = recipe_name
    context["ingredients"] = ingredients
    context["recipe_id"] = id

    service = RecipeService(db)

    try:
        if id is not None:
            recipe = service.update(id, recipe_name, ingredients)
            context["success_message"] = "Recipe updated successfully"
        else:
            recipe = service.create(recipe_name, ingredients)
            context["success_message"] = "Recipe created successfully"

        context["recipe_name"] = recipe.name
        context["ingredients"] = recipe.ingredients
        context["recipe_id"] = recipe.id

    except ValidationError as exc:
        field_errors: dict[str, str] = {}
        details = getattr(exc, "errors", None)

        if isinstance(details, dict):
            field_errors.update(details)
        else:
            message = str(exc)
            lowered = message.lower()
            if "name" in lowered and "ingredient" not in lowered:
                field_errors["recipe_name"] = message
            elif "ingredient" in lowered and "name" not in lowered:
                field_errors["ingredients"] = message
            else:
                if not recipe_name or not recipe_name.strip():
                    field_errors["recipe_name"] = "Recipe name is required"
                if not ingredients or not ingredients.strip():
                    field_errors["ingredients"] = "Ingredients is required"
                if not field_errors:
                    context["error_message"] = message

        if not field_errors and not context["error_message"]:
            if not recipe_name or not recipe_name.strip():
                field_errors["recipe_name"] = "Recipe name is required"
            if not ingredients or not ingredients.strip():
                field_errors["ingredients"] = "Ingredients is required"

        context["field_errors"] = field_errors

    return templates.TemplateResponse(request, "recipe.html", context)


@router.get("/")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    service = RecipeService(db)
    recipes = service.list_all()

    context = {
        "recipes": recipes,
        "success_message": "",
        "field_errors": {},
        "error_message": "",
    }

    return templates.TemplateResponse(request, "index.html", context)
