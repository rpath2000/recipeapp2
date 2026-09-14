"""Unit tests for RecipeService.

Uses the shared db_session fixture (provided by the platform) rather than
creating a private engine, so behaviour is verified against the same
schema/session machinery the application uses at runtime.
"""
from __future__ import annotations

import time

import pytest

from app.contracts import ValidationError
from app.services import RecipeService


def test_create_with_valid_data_returns_recipe_data_with_id(db_session):
    service = RecipeService(db_session)

    dto = service.create(name="Pancakes", ingredients="Flour, eggs, milk")

    assert dto.id is not None
    assert isinstance(dto.id, int)
    assert dto.name == "Pancakes"
    assert dto.ingredients == "Flour, eggs, milk"
    assert dto.created_at is not None


def test_create_raises_validation_error_when_name_empty_after_strip(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValidationError) as exc_info:
        service.create(name="   ", ingredients="Flour, eggs, milk")

    assert exc_info.value.field == "name"
    assert "empty" in exc_info.value.message.lower()


def test_create_raises_validation_error_when_ingredients_empty_after_strip(db_session):
    service = RecipeService(db_session)

    with pytest.raises(ValidationError) as exc_info:
        service.create(name="Pancakes", ingredients="   ")

    assert exc_info.value.field == "ingredients"
    assert "empty" in exc_info.value.message.lower()


def test_create_raises_validation_error_when_name_exceeds_max_length(db_session):
    service = RecipeService(db_session)
    long_name = "a" * 121

    with pytest.raises(ValidationError) as exc_info:
        service.create(name=long_name, ingredients="Flour")

    assert exc_info.value.field == "name"
    assert "120" in exc_info.value.message


def test_create_raises_validation_error_when_ingredients_exceed_max_length(db_session):
    service = RecipeService(db_session)
    long_ingredients = "a" * 4001

    with pytest.raises(ValidationError) as exc_info:
        service.create(name="Pancakes", ingredients=long_ingredients)

    assert exc_info.value.field == "ingredients"
    assert "4000" in exc_info.value.message


def test_update_modifies_existing_recipe_and_returns_updated_data(db_session):
    service = RecipeService(db_session)
    created = service.create(name="Pancakes", ingredients="Flour, eggs, milk")

    updated = service.update(
        recipe_id=created.id, name="Waffles", ingredients="Flour, eggs, sugar"
    )

    assert updated.id == created.id
    assert updated.name == "Waffles"
    assert updated.ingredients == "Flour, eggs, sugar"

    fetched = service.get_by_id(created.id)
    assert fetched.name == "Waffles"
    assert fetched.ingredients == "Flour, eggs, sugar"


def test_update_raises_lookup_error_for_nonexistent_id(db_session):
    service = RecipeService(db_session)

    with pytest.raises(LookupError):
        service.update(recipe_id=999999, name="Waffles", ingredients="Flour")


def test_update_raises_validation_error_for_invalid_name(db_session):
    service = RecipeService(db_session)
    created = service.create(name="Pancakes", ingredients="Flour, eggs, milk")

    with pytest.raises(ValidationError) as exc_info:
        service.update(recipe_id=created.id, name="   ", ingredients="Flour")

    assert exc_info.value.field == "name"


def test_get_by_id_returns_none_for_nonexistent_id(db_session):
    service = RecipeService(db_session)

    result = service.get_by_id(999999)

    assert result is None


def test_get_by_id_returns_recipe_data_for_existing_id(db_session):
    service = RecipeService(db_session)
    created = service.create(name="Pancakes", ingredients="Flour, eggs, milk")

    result = service.get_by_id(created.id)

    assert result is not None
    assert result.id == created.id
    assert result.name == "Pancakes"


def test_list_all_orders_recipes_newest_first(db_session):
    service = RecipeService(db_session)

    first = service.create(name="First", ingredients="a")
    time.sleep(0.01)
    second = service.create(name="Second", ingredients="b")
    time.sleep(0.01)
    third = service.create(name="Third", ingredients="c")

    results = service.list_all()

    ids_in_order = [r.id for r in results]
    assert ids_in_order.index(third.id) < ids_in_order.index(second.id)
    assert ids_in_order.index(second.id) < ids_in_order.index(first.id)


def test_list_all_returns_empty_list_when_no_recipes(db_session):
    service = RecipeService(db_session)

    results = service.list_all()

    assert results == []
