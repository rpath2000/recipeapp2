"""
Contract/unit tests for the recipes router.

These tests exercise the FastAPI app with the RecipeService and
auth dependency overridden with in-memory fakes so that no real
database or SSO provider is required.
"""
from datetime import datetime, timezone
from typing import Dict, Optional

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.contracts import RecipeCreateIn, RecipeListOut, RecipeOut, RecipeUpdateIn
from app.models.database import get_db
from app.security.sso_middleware import get_current_user
import app.routers.recipes as recipes_module


CURRENT_USER_ID = "user-owner-1"
OTHER_USER_ID = "user-other-2"


class FakeRecipeService:
    """In-memory fake implementing the RecipeService contract."""

    def __init__(self) -> None:
        self._store: Dict[str, RecipeOut] = {}
        self._counter = 0

    def create_recipe(self, recipe_in: RecipeCreateIn, owner_id: str, db) -> RecipeOut:
        self._counter += 1
        recipe_id = f"recipe-{self._counter}"
        now = datetime.now(timezone.utc)
        recipe = RecipeOut(
            id=recipe_id,
            name=recipe_in.name,
            description=recipe_in.description,
            ingredients=recipe_in.ingredients,
            instructions=recipe_in.instructions,
            category=recipe_in.category,
            image_url=recipe_in.image_url,
            created_at=now,
            updated_at=now,
            owner_id=owner_id,
        )
        self._store[recipe_id] = recipe
        return recipe

    def get_recipe(self, recipe_id: str, db) -> Optional[RecipeOut]:
        return self._store.get(recipe_id)

    def list_recipes(self, page: int, page_size: int, db) -> RecipeListOut:
        items = list(self._store.values())
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]
        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        return RecipeListOut(items=page_items, total=total, page=page, page_size=page_size, total_pages=total_pages)

    def update_recipe(self, recipe_id: str, recipe_in: RecipeUpdateIn, owner_id: str, db) -> RecipeOut:
        existing = self._store.get(recipe_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        if existing.owner_id != owner_id:
            raise PermissionError("not owner")
        updated = RecipeOut(
            id=existing.id,
            name=recipe_in.name,
            description=recipe_in.description,
            ingredients=recipe_in.ingredients,
            instructions=recipe_in.instructions,
            category=recipe_in.category,
            image_url=recipe_in.image_url,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc),
            owner_id=existing.owner_id,
        )
        self._store[recipe_id] = updated
        return updated

    def delete_recipe(self, recipe_id: str, owner_id: str, db) -> None:
        existing = self._store.get(recipe_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        if existing.owner_id != owner_id:
            raise PermissionError("not owner")
        del self._store[recipe_id]

    def search_recipes(self, query: str, page: int, page_size: int, db) -> RecipeListOut:
        matches = [r for r in self._store.values() if query.lower() in r.name.lower()]
        total = len(matches)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = matches[start:end]
        total_pages = max(1, (total + page_size - 1) // page_size)
        return RecipeListOut(items=page_items, total=total, page=page, page_size=page_size, total_pages=total_pages)

    def filter_recipes_by_category(self, category: str, page: int, page_size: int, db) -> RecipeListOut:
        matches = [r for r in self._store.values() if r.category == category]
        total = len(matches)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = matches[start:end]
        total_pages = max(1, (total + page_size - 1) // page_size)
        return RecipeListOut(items=page_items, total=total, page=page, page_size=page_size, total_pages=total_pages)

    def upload_image(self, file, recipe_id: str) -> str:
        return f"https://images.example.com/{recipe_id}.png"

    def get_image_url(self, recipe_id: str) -> Optional[str]:
        existing = self._store.get(recipe_id)
        if existing is None:
            return None
        return existing.image_url or f"https://images.example.com/{recipe_id}.png"


def _fake_get_db():
    yield None


def _fake_get_current_user():
    return CURRENT_USER_ID


@pytest.fixture()
def app_client(monkeypatch):
    fake_service = FakeRecipeService()
    monkeypatch.setattr(recipes_module, "_service", fake_service)

    app = FastAPI()
    app.include_router(recipes_module.router)
    app.dependency_overrides[get_db] = _fake_get_db
    app.dependency_overrides[get_current_user] = _fake_get_current_user

    client = TestClient(app)
    return client, fake_service, app


def _valid_payload(name="Pasta Bolognese", category="dinner"):
    return {
        "name": name,
        "description": "Classic Italian dish",
        "ingredients": "pasta, beef, tomato sauce",
        "instructions": "Cook pasta. Cook sauce. Combine.",
        "category": category,
        "image_url": None,
    }


def test_create_recipe_returns_201_and_recipe_json(app_client):
    client, _, _ = app_client
    response = client.post("/api/v1/recipes", json=_valid_payload())

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["name"] == "Pasta Bolognese"
    assert body["owner_id"] == CURRENT_USER_ID
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_create_recipe_blank_name_returns_422(app_client):
    client, _, _ = app_client
    payload = _valid_payload(name="")
    response = client.post("/api/v1/recipes", json=payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_update_recipe_by_non_owner_returns_403(app_client):
    client, service, app = app_client
    created = client.post("/api/v1/recipes", json=_valid_payload()).json()
    recipe_id = created["id"]

    app.dependency_overrides[get_current_user] = lambda: OTHER_USER_ID

    update_payload = {
        "name": "Updated Name",
        "description": "Updated description",
        "ingredients": "updated ingredients",
        "instructions": "updated instructions",
        "category": "dinner",
        "image_url": None,
    }
    response = client.put(f"/api/v1/recipes/{recipe_id}", json=update_payload)

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_delete_recipe_by_owner_returns_204_and_removes(app_client):
    client, service, _ = app_client
    created = client.post("/api/v1/recipes", json=_valid_payload()).json()
    recipe_id = created["id"]

    response = client.delete(f"/api/v1/recipes/{recipe_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert service.get_recipe(recipe_id, db=None) is None

    get_response = client.get(f"/api/v1/recipes/{recipe_id}")
    assert get_response.status_code == status.HTTP_404_NOT_FOUND


def test_search_recipes_returns_filtered_results(app_client):
    client, _, _ = app_client
    client.post("/api/v1/recipes", json=_valid_payload(name="Pasta Bolognese"))
    client.post("/api/v1/recipes", json=_valid_payload(name="Chicken Curry"))
    client.post("/api/v1/recipes", json=_valid_payload(name="Pasta Carbonara"))

    response = client.get("/api/v1/recipes/search", params={"q": "Pasta"})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 2
    names = {item["name"] for item in body["items"]}
    assert names == {"Pasta Bolognese", "Pasta Carbonara"}
