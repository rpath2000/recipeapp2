"""
Unit tests for RecipeService covering create/read/update/delete/list/search
behaviors including validation and ownership authorization.

Uses an in-memory SQLite database via SQLAlchemy to exercise real query
logic (pagination, case-insensitive search) without external dependencies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.contracts import RecipeCreateIn, RecipeOut, RecipeUpdateIn
from app.models.database import Base
from app.models.recipe import Recipe
from app.services.recipe_service import (
    AuthorizationError,
    NotFoundError,
    RecipeService,
    ValidationError,
)


@pytest.fixture()
def db_session():
    """Provide an isolated in-memory SQLite session per test."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def service():
    return RecipeService()


def _valid_create_in(**overrides) -> RecipeCreateIn:
    base = dict(
        name="Chocolate Cake",
        description="A rich, moist chocolate cake.",
        ingredients="flour, sugar, cocoa, eggs",
        instructions="Mix and bake at 350F for 30 minutes.",
        category="Dessert",
        image_url=None,
    )
    base.update(overrides)
    return RecipeCreateIn(**base)


def _valid_update_in(**overrides) -> RecipeUpdateIn:
    base = dict(
        name="Updated Cake",
        description="An updated description.",
        ingredients="flour, sugar, cocoa, eggs, vanilla",
        instructions="Mix, bake, and cool.",
        category="Dessert",
        image_url=None,
    )
    base.update(overrides)
    return RecipeUpdateIn(**base)


def _seed_recipe(db_session, owner_id: str = "owner-1", **overrides) -> Recipe:
    defaults = dict(
        id=str(uuid.uuid4()),
        name="Seed Recipe",
        description="Seed description",
        ingredients="seed ingredients",
        instructions="seed instructions",
        category="Breakfast",
        image_url=None,
        owner_id=owner_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    recipe = Recipe(**defaults)
    db_session.add(recipe)
    db_session.commit()
    db_session.refresh(recipe)
    return recipe


class TestCreateRecipe:
    def test_create_recipe_with_valid_data_succeeds(self, service, db_session):
        recipe_in = _valid_create_in()
        result = service.create_recipe(recipe_in, owner_id="owner-1", db=db_session)

        assert isinstance(result, RecipeOut)
        assert result.name == "Chocolate Cake"
        assert result.owner_id == "owner-1"
        assert result.id is not None
        assert result.created_at is not None
        assert result.updated_at is not None

        persisted = db_session.query(Recipe).filter(Recipe.id == result.id).first()
        assert persisted is not None
        assert persisted.owner_id == "owner-1"

    def test_create_recipe_with_blank_name_raises_validation_error(
        self, service, db_session
    ):
        recipe_in = _valid_create_in(name="   ")

        with pytest.raises(ValidationError) as excinfo:
            service.create_recipe(recipe_in, owner_id="owner-1", db=db_session)

        assert "name" in excinfo.value.message.lower()
        assert excinfo.value.field == "name"

    @pytest.mark.parametrize(
        "field",
        ["description", "ingredients", "instructions", "category"],
    )
    def test_create_recipe_with_blank_required_field_raises_validation_error(
        self, service, db_session, field
    ):
        recipe_in = _valid_create_in(**{field: ""})

        with pytest.raises(ValidationError) as excinfo:
            service.create_recipe(recipe_in, owner_id="owner-1", db=db_session)

        assert excinfo.value.field == field

    def test_create_recipe_with_blank_owner_id_raises_validation_error(
        self, service, db_session
    ):
        recipe_in = _valid_create_in()

        with pytest.raises(ValidationError):
            service.create_recipe(recipe_in, owner_id="  ", db=db_session)


class TestGetRecipe:
    def test_get_existing_recipe_returns_dto(self, service, db_session):
        seeded = _seed_recipe(db_session)
        result = service.get_recipe(seeded.id, db_session)

        assert result is not None
        assert result.id == seeded.id
        assert result.name == seeded.name

    def test_get_nonexistent_recipe_returns_none(self, service, db_session):
        result = service.get_recipe(str(uuid.uuid4()), db_session)
        assert result is None


class TestUpdateRecipe:
    def test_update_recipe_by_owner_succeeds(self, service, db_session):
        seeded = _seed_recipe(db_session, owner_id="owner-1")
        update_in = _valid_update_in()

        result = service.update_recipe(
            seeded.id, update_in, owner_id="owner-1", db=db_session
        )

        assert result.name == "Updated Cake"
        assert result.description == "An updated description."

    def test_update_recipe_by_non_owner_returns_authorization_error(
        self, service, db_session
    ):
        seeded = _seed_recipe(db_session, owner_id="owner-1")
        update_in = _valid_update_in()

        with pytest.raises(AuthorizationError):
            service.update_recipe(
                seeded.id, update_in, owner_id="owner-2", db=db_session
            )

    def test_update_nonexistent_recipe_raises_not_found(self, service, db_session):
        update_in = _valid_update_in()

        with pytest.raises(NotFoundError):
            service.update_recipe(
                str(uuid.uuid4()), update_in, owner_id="owner-1", db=db_session
            )

    def test_update_recipe_with_blank_field_raises_validation_error(
        self, service, db_session
    ):
        seeded = _seed_recipe(db_session, owner_id="owner-1")
        update_in = _valid_update_in(instructions="")

        with pytest.raises(ValidationError):
            service.update_recipe(
                seeded.id, update_in, owner_id="owner-1", db=db_session
            )


class TestDeleteRecipe:
    def test_delete_recipe_by_owner_succeeds(self, service, db_session):
        seeded = _seed_recipe(db_session, owner_id="owner-1")

        service.delete_recipe(seeded.id, owner_id="owner-1", db=db_session)

        assert db_session.query(Recipe).filter(Recipe.id == seeded.id).first() is None

    def test_delete_recipe_by_non_owner_returns_authorization_error(
        self, service, db_session
    ):
        seeded = _seed_recipe(db_session, owner_id="owner-1")

        with pytest.raises(AuthorizationError):
            service.delete_recipe(seeded.id, owner_id="intruder", db=db_session)

        assert db_session.query(Recipe).filter(Recipe.id == seeded.id).first() is not None

    def test_delete_nonexistent_recipe_raises_not_found(self, service, db_session):
        with pytest.raises(NotFoundError):
            service.delete_recipe(str(uuid.uuid4()), owner_id="owner-1", db=db_session)


class TestListRecipes:
    def test_list_recipes_returns_paginated_results_with_metadata(
        self, service, db_session
    ):
        for i in range(25):
            _seed_recipe(db_session, name=f"Recipe {i}", owner_id="owner-1")

        page1 = service.list_recipes(page=1, page_size=10, db=db_session)
        assert len(page1.items) == 10
        assert page1.total == 25
        assert page1.page == 1
        assert page1.page_size == 10
        assert page1.total_pages == 3

        page3 = service.list_recipes(page=3, page_size=10, db=db_session)
        assert len(page3.items) == 5
        assert page3.total == 25
        assert page3.page == 3

    def test_list_recipes_exactly_10_items_default_page(self, service, db_session):
        for i in range(12):
            _seed_recipe(db_session, name=f"Item {i}", owner_id="owner-1")

        result = service.list_recipes(page=1, page_size=10, db=db_session)

        assert len(result.items) == 10
        assert result.total == 12
        assert result.total_pages == 2

    def test_list_recipes_empty_returns_zero_total(self, service, db_session):
        result = service.list_recipes(page=1, page_size=10, db=db_session)
        assert result.items == []
        assert result.total == 0
        assert result.total_pages == 0


class TestSearchRecipes:
    def test_search_by_partial_name_case_insensitive(self, service, db_session):
        _seed_recipe(db_session, name="Spicy Chicken Curry", owner_id="owner-1")
        _seed_recipe(db_session, name="Chicken Noodle Soup", owner_id="owner-1")
        _seed_recipe(db_session, name="Beef Stew", owner_id="owner-1")

        result = service.search_recipes("CHICKEN", page=1, page_size=10, db=db_session)

        names = {item.name for item in result.items}
        assert names == {"Spicy Chicken Curry", "Chicken Noodle Soup"}
        assert result.total == 2

    def test_search_with_lowercase_partial_match(self, service, db_session):
        _seed_recipe(db_session, name="Vegetable Lasagna", owner_id="owner-1")

        result = service.search_recipes("lasagna", page=1, page_size=10, db=db_session)

        assert result.total == 1
        assert result.items[0].name == "Vegetable Lasagna"

    def test_search_with_blank_query_returns_empty(self, service, db_session):
        _seed_recipe(db_session, name="Anything", owner_id="owner-1")

        result = service.search_recipes("   ", page=1, page_size=10, db=db_session)

        assert result.items == []
        assert result.total == 0

    def test_search_with_no_matches_returns_empty(self, service, db_session):
        _seed_recipe(db_session, name="Pancakes", owner_id="owner-1")

        result = service.search_recipes("waffles", page=1, page_size=10, db=db_session)

        assert result.items == []
        assert result.total == 0


class TestFilterByCategory:
    def test_filter_by_category_case_insensitive(self, service, db_session):
        _seed_recipe(db_session, name="A", category="Dessert", owner_id="owner-1")
        _seed_recipe(db_session, name="B", category="dessert", owner_id="owner-1")
        _seed_recipe(db_session, name="C", category="Main Course", owner_id="owner-1")

        result = service.filter_recipes_by_category(
            "DESSERT", page=1, page_size=10, db=db_session
        )

        assert result.total == 2
        names = {item.name for item in result.items}
        assert names == {"A", "B"}

    def test_filter_with_blank_category_returns_empty(self, service, db_session):
        _seed_recipe(db_session, category="Dessert", owner_id="owner-1")

        result = service.filter_recipes_by_category("", page=1, page_size=10, db=db_session)

        assert result.items == []
        assert result.total == 0
