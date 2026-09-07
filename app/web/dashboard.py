"""Dashboard route: lists all recipes, ordered by updated_at DESC, id DESC."""
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models import get_db
from app.services.recipe_service import RecipeService

router = APIRouter()

templates = Jinja2Templates(directory="app/web/templates")


@router.get("/")
def dashboard(request: Request, error_message: str = "", db: Session = Depends(get_db)):
    """Render the recipe dashboard with all recipes ordered for display."""
    service = RecipeService(db)
    recipes = service.list_all()

    ordered = sorted(
        recipes,
        key=lambda r: (r.updated_at, r.id),
        reverse=True,
    )

    context = {
        "recipes": ordered,
        "success_message": "",
        "error_message": error_message,
        "field_errors": {},
    }
    return templates.TemplateResponse(request, "index.html", context)
