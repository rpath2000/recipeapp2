from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.contracts import ValidationError
from app.models import get_db
from app.services.recipe_service import RecipeService

router = APIRouter()

templates = Jinja2Templates(directory="app/web/templates")


@router.get("/recipe")
async def get_recipe_form(request: Request, id: str | None = None, db: Session = Depends(get_db)):
    name_value = ""
    ingredients_value = ""

    if id:
        try:
            recipe_uuid = UUID(id)
        except ValueError:
            recipe_uuid = None

        if recipe_uuid is not None:
            service = RecipeService(db)
            recipe = service.get_recipe_by_id(recipe_uuid)
            if recipe is not None:
                name_value = recipe.name
                ingredients_value = recipe.ingredients

    context = {
        "success_message": "",
        "field_errors": {},
        "error_message": "",
        "name": name_value,
        "ingredients": ingredients_value,
        "recipe_id": id or "",
    }
    return templates.TemplateResponse(request, "recipe.html", context)


@router.post("/recipe")
async def post_recipe_form(
    request: Request,
    name: str = Form(...),
    ingredients: str = Form(...),
    id: str | None = Form(None),
    db: Session = Depends(get_db),
):
    service = RecipeService(db)

    recipe_uuid: UUID | None = None
    if id:
        try:
            recipe_uuid = UUID(id)
        except ValueError:
            recipe_uuid = None

    success_message = ""
    field_errors: dict[str, str] = {}
    error_message = ""

    try:
        if recipe_uuid is not None:
            saved = service.update_recipe(recipe_uuid, name, ingredients)
        else:
            saved = service.create_recipe(name, ingredients)
        success_message = "Recipe saved successfully."
        name_value = saved.name
        ingredients_value = saved.ingredients
        recipe_id_value = str(saved.id)
    except ValidationError as exc:
        message = str(exc)
        lowered = message.lower()
        if "ingredient" in lowered:
            field_errors["ingredients"] = message
        elif "name" in lowered:
            field_errors["name"] = message
        else:
            error_message = message
        name_value = name
        ingredients_value = ingredients
        recipe_id_value = id or ""

    context = {
        "success_message": success_message,
        "field_errors": field_errors,
        "error_message": error_message,
        "name": name_value,
        "ingredients": ingredients_value,
        "recipe_id": recipe_id_value,
    }
    return templates.TemplateResponse(request, "recipe.html", context)


@router.get("/")
async def get_dashboard(request: Request, db: Session = Depends(get_db)):
    service = RecipeService(db)
    recipes = service.list_recipes()
    recipes_sorted = sorted(recipes, key=lambda r: r.created_at, reverse=True)

    context = {
        "success_message": "",
        "field_errors": {},
        "error_message": "",
        "recipes": recipes_sorted,
    }
    return templates.TemplateResponse(request, "index.html", context)
