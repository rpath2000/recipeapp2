"""Unit tests for RecipeService."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.contracts import ValidationError
from app.models import Base
from app.services.recipe_service import RecipeService


@pytest.fixture()
def db_session(tmp_path):
    """Provide an isolated, file-based SQLite session per test."""
    db_path = tmp_path / "test_recipes.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_create_recipe_persists_and_returns_dto(db_session):
    service = RecipeService(db_session)

    result = service.create_recipe(name="Pancakes", ingredients="Flour, eggs, milk")

    assert result.id is not None
    assert result.name == "Pancakes"
    assert result.ingredients == "Flour, eggs, milk"
    assert result.created_at is not None

    fetched = service.get_recipe_by_id(result.id)
    assert fetched is not None
    assert fetched.name == "Pancakes"
    assert fetched.ingredients == "Flour, eggs, milk"


def test_update_recipe_modifies_existing_recipe(db_session):
    service = RecipeService(db_session)
    created = service.create_recipe(name="Original", ingredients="Original ingredients")

    updated = service.update_recipe(
        created.id, name="Updated Name", ingredients="Updated ingredients"
    )

    assert updated.id == created.id
    assert updated.name == "Updated Name"
    assert updated.ingredients == "Updated ingredients"

    fetched = service.get_recipe_by_id(created.id)
    assert fetched.name == "Updated Name"
    assert fetched.ingredients == "Updated ingredients"


def test_update_recipe_raises_for_missing_id(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValueError):
        service.update_recipe(uuid4(), name="Name", ingredients="Ingredients")


def test_get_recipe_by_id_returns_none_when_missing(db_session):
    service = RecipeService(db_session)

    assert service.get_recipe_by_id(uuid4()) is None


def test_list_recipes_orders_by_created_at_descending(db_session):
    service = RecipeService(db_session)

    first = service.create_recipe(name="First", ingredients="Ingredients one")
    time.sleep(0.01)
    second = service.create_recipe(name="Second", ingredients="Ingredients two")
    time.sleep(0.01)
    third = service.create_recipe(name="Third", ingredients="Ingredients three")

    results = service.list_recipes()

    assert [r.id for r in results] == [third.id, second.id, first.id]


def test_create_recipe_raises_validation_error_for_empty_name(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValidationError):
        service.create_recipe(name="", ingredients="Some ingredients")


def test_create_recipe_raises_validation_error_for_whitespace_only_name(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValidationError):
        service.create_recipe(name="   ", ingredients="Some ingredients")


def test_create_recipe_raises_validation_error_for_name_too_long(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValidationError):
        service.create_recipe(name="a" * 121, ingredients="Some ingredients")


def test_create_recipe_raises_validation_error_for_empty_ingredients(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValidationError):
        service.create_recipe(name="Valid Name", ingredients="")


def test_create_recipe_raises_validation_error_for_whitespace_only_ingredients(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValidationError):
        service.create_recipe(name="Valid Name", ingredients="    ")


def test_create_recipe_raises_validation_error_for_ingredients_too_long(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValidationError):
        service.create_recipe(name="Valid Name", ingredients="a" * 4001)


def test_create_recipe_allows_max_length_boundaries(db_session):
    service = RecipeService(db_session)

    result = service.create_recipe(name="a" * 120, ingredients="b" * 4000)

    assert len(result.name) == 120
    assert len(result.ingredients) == 4000
