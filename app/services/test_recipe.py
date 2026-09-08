"""Unit tests for RecipeService."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.contracts import ValidationError
from app.models import Base
from app.services.recipe import RecipeService


@pytest.fixture()
def db() -> Session:
    """Provide an isolated in-memory SQLite session per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def service() -> RecipeService:
    return RecipeService()


def test_create_recipe_with_valid_inputs_inserts_and_returns_dto(service, db):
    dto = service.create_recipe("Pancakes", "Flour, Milk, Eggs", db)

    assert dto.id is not None
    assert dto.name == "Pancakes"
    assert dto.ingredients == "Flour, Milk, Eggs"
    assert dto.created_at is not None
    assert dto.updated_at is not None

    # Confirm it was actually persisted and retrievable.
    fetched = service.get_recipe(dto.id, db)
    assert fetched is not None
    assert fetched.name == "Pancakes"
    assert fetched.ingredients == "Flour, Milk, Eggs"


def test_create_recipe_with_empty_name_after_trim_raises_validation_error(service, db):
    with pytest.raises(ValidationError) as exc_info:
        service.create_recipe("   ", "Flour, Milk, Eggs", db)

    assert "name" in str(exc_info.value)


def test_create_recipe_with_name_over_120_chars_raises_validation_error(service, db):
    long_name = "a" * 121

    with pytest.raises(ValidationError) as exc_info:
        service.create_recipe(long_name, "Flour, Milk, Eggs", db)

    assert "name" in str(exc_info.value)


def test_create_recipe_with_empty_ingredients_raises_validation_error(service, db):
    with pytest.raises(ValidationError) as exc_info:
        service.create_recipe("Pancakes", "   ", db)

    assert "ingredients" in str(exc_info.value)


def test_create_recipe_with_ingredients_over_4000_chars_raises_validation_error(
    service, db
):
    long_ingredients = "a" * 4001

    with pytest.raises(ValidationError) as exc_info:
        service.create_recipe("Pancakes", long_ingredients, db)

    assert "ingredients" in str(exc_info.value)


def test_update_recipe_with_valid_inputs_updates_and_refreshes_updated_at(
    service, db
):
    created = service.create_recipe("Pancakes", "Flour, Milk, Eggs", db)
    original_updated_at = created.updated_at

    # Ensure measurable time difference between create and update.
    time.sleep(0.01)

    updated = service.update_recipe(
        created.id, "Waffles", "Flour, Milk, Eggs, Sugar", db
    )

    assert updated.id == created.id
    assert updated.name == "Waffles"
    assert updated.ingredients == "Flour, Milk, Eggs, Sugar"
    assert updated.updated_at >= original_updated_at

    fetched = service.get_recipe(created.id, db)
    assert fetched.name == "Waffles"
    assert fetched.ingredients == "Flour, Milk, Eggs, Sugar"


def test_update_recipe_with_invalid_name_raises_validation_error(service, db):
    created = service.create_recipe("Pancakes", "Flour, Milk, Eggs", db)

    with pytest.raises(ValidationError) as exc_info:
        service.update_recipe(created.id, "", "Flour, Milk, Eggs", db)

    assert "name" in str(exc_info.value)


def test_update_recipe_with_nonexistent_id_raises_validation_error(service, db):
    with pytest.raises(ValidationError):
        service.update_recipe(9999, "Pancakes", "Flour, Milk, Eggs", db)


def test_get_recipe_returns_none_when_not_found(service, db):
    assert service.get_recipe(9999, db) is None


def test_list_recipes_returns_recipes_ordered_by_updated_at_desc_then_id_desc(
    service, db
):
    first = service.create_recipe("Recipe A", "Ingredients A", db)
    time.sleep(0.01)
    second = service.create_recipe("Recipe B", "Ingredients B", db)
    time.sleep(0.01)
    third = service.create_recipe("Recipe C", "Ingredients C", db)

    # Update the first recipe so it becomes the most recently updated.
    time.sleep(0.01)
    service.update_recipe(first.id, "Recipe A Updated", "Ingredients A Updated", db)

    results = service.list_recipes(db)
    ids_in_order = [r.id for r in results]

    assert ids_in_order[0] == first.id
    assert set(ids_in_order[1:]) == {second.id, third.id}
    # Among untouched recipes, higher id (created later) sorts first
    # because updated_at defaults are ordered by creation time too.
    assert ids_in_order[1] == third.id
    assert ids_in_order[2] == second.id
