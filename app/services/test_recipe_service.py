"""Unit tests for RecipeService.

Uses an in-memory SQLite database wired through the shared
``app.models`` ORM models to exercise the service against a real
SQLAlchemy session, matching production wiring while remaining fast
and isolated.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.contracts import (
    RecipeCreateDTO,
    RecipeNotFoundError,
    RecipeUpdateDTO,
    ValidationError,
)
from app.models import Base, Recipe
from app.services.recipe_service import RecipeService


@pytest.fixture()
def db_session():
    """Provide a fresh in-memory SQLite session per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session: Session = session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def service(db_session: Session) -> RecipeService:
    return RecipeService(db_session)


class TestCreateValidation:
    """Verify create() rejects invalid input with field-specific errors."""

    def test_rejects_empty_name(self, service: RecipeService):
        with pytest.raises(ValidationError) as exc_info:
            service.create(RecipeCreateDTO(name="", ingredients="Flour, eggs"))

        errors = exc_info.value.errors
        assert "name" in errors
        assert "ingredients" not in errors

    def test_rejects_whitespace_only_name(self, service: RecipeService):
        with pytest.raises(ValidationError) as exc_info:
            service.create(
                RecipeCreateDTO(name="   \t  ", ingredients="Flour, eggs")
            )

        errors = exc_info.value.errors
        assert "name" in errors

    def test_rejects_empty_ingredients(self, service: RecipeService):
        with pytest.raises(ValidationError) as exc_info:
            service.create(RecipeCreateDTO(name="Cake", ingredients=""))

        errors = exc_info.value.errors
        assert "ingredients" in errors
        assert "name" not in errors

    def test_rejects_whitespace_only_ingredients(self, service: RecipeService):
        with pytest.raises(ValidationError) as exc_info:
            service.create(RecipeCreateDTO(name="Cake", ingredients="   \n\t  "))

        errors = exc_info.value.errors
        assert "ingredients" in errors

    def test_rejects_both_fields_invalid_with_both_messages(
        self, service: RecipeService
    ):
        with pytest.raises(ValidationError) as exc_info:
            service.create(RecipeCreateDTO(name="", ingredients=""))

        errors = exc_info.value.errors
        assert "name" in errors
        assert "ingredients" in errors

    def test_rejects_name_over_max_length(self, service: RecipeService):
        with pytest.raises(ValidationError) as exc_info:
            service.create(
                RecipeCreateDTO(name="a" * 121, ingredients="valid ingredients")
            )

        assert "name" in exc_info.value.errors

    def test_rejects_ingredients_over_max_length(self, service: RecipeService):
        with pytest.raises(ValidationError) as exc_info:
            service.create(
                RecipeCreateDTO(name="Cake", ingredients="a" * 4001)
            )

        assert "ingredients" in exc_info.value.errors

    def test_accepts_boundary_lengths(self, service: RecipeService):
        recipe_id = service.create(
            RecipeCreateDTO(name="a" * 120, ingredients="b" * 4000)
        )
        assert isinstance(recipe_id, int)


class TestControlCharacterStripping:
    """Verify non-printable control chars are stripped, newline/tab kept."""

    def test_strips_control_chars_but_preserves_newline_and_tab(
        self, service: RecipeService
    ):
        raw_ingredients = "Flour\x00\x01\n2 eggs\tsugar\x07"
        recipe_id = service.create(
            RecipeCreateDTO(name="Cake", ingredients=raw_ingredients)
        )

        result = service.get_by_id(recipe_id)

        assert result.ingredients == "Flour\n2 eggs\tsugar"
        assert "\x00" not in result.ingredients
        assert "\x01" not in result.ingredients
        assert "\x07" not in result.ingredients
        assert "\n" in result.ingredients
        assert "\t" in result.ingredients

    def test_strips_control_chars_from_name(self, service: RecipeService):
        raw_name = "Cho\x00colate\x1fCake"
        recipe_id = service.create(
            RecipeCreateDTO(name=raw_name, ingredients="cocoa, sugar")
        )

        result = service.get_by_id(recipe_id)

        assert result.name == "ChocolateCake"

    def test_trims_after_stripping_control_chars(self, service: RecipeService):
        # Control chars sandwiched around leading/trailing whitespace
        # should still result in a trimmed value.
        recipe_id = service.create(
            RecipeCreateDTO(name="  Cake  ", ingredients="  Flour  ")
        )

        result = service.get_by_id(recipe_id)

        assert result.name == "Cake"
        assert result.ingredients == "Flour"


class TestUpdate:
    """Verify update() error handling and success path."""

    def test_raises_not_found_for_nonexistent_id(self, service: RecipeService):
        with pytest.raises(RecipeNotFoundError):
            service.update(
                999999, RecipeUpdateDTO(name="New Name", ingredients="New stuff")
            )

    def test_raises_validation_error_for_invalid_fields(
        self, service: RecipeService
    ):
        recipe_id = service.create(
            RecipeCreateDTO(name="Cake", ingredients="Flour, eggs")
        )

        with pytest.raises(ValidationError) as exc_info:
            service.update(recipe_id, RecipeUpdateDTO(name="", ingredients=""))

        errors = exc_info.value.errors
        assert "name" in errors
        assert "ingredients" in errors

    def test_validation_failure_does_not_mutate_existing_record(
        self, service: RecipeService
    ):
        recipe_id = service.create(
            RecipeCreateDTO(name="Cake", ingredients="Flour, eggs")
        )

        with pytest.raises(ValidationError):
            service.update(recipe_id, RecipeUpdateDTO(name="", ingredients="x"))

        unchanged = service.get_by_id(recipe_id)
        assert unchanged.name == "Cake"
        assert unchanged.ingredients == "Flour, eggs"

    def test_update_success_persists_sanitized_values(
        self, service: RecipeService
    ):
        recipe_id = service.create(
            RecipeCreateDTO(name="Cake", ingredients="Flour, eggs")
        )

        service.update(
            recipe_id,
            RecipeUpdateDTO(name="  New\x00Cake  ", ingredients="  Sugar\n  "),
        )

        updated = service.get_by_id(recipe_id)
        assert updated.name == "NewCake"
        assert updated.ingredients == "Sugar"

    def test_update_malformed_id_raises_not_found(self, service: RecipeService):
        with pytest.raises(RecipeNotFoundError):
            service.update(
                "not-a-number",
                RecipeUpdateDTO(name="Name", ingredients="Ingredients"),
            )


class TestGetById:
    """Verify get_by_id() error handling for malformed/missing ids."""

    def test_raises_not_found_for_nonexistent_numeric_id(
        self, service: RecipeService
    ):
        with pytest.raises(RecipeNotFoundError):
            service.get_by_id(424242)

    def test_raises_not_found_for_non_numeric_string_id(
        self, service: RecipeService
    ):
        with pytest.raises(RecipeNotFoundError):
            service.get_by_id("abc")

    def test_raises_not_found_for_empty_string_id(self, service: RecipeService):
        with pytest.raises(RecipeNotFoundError):
            service.get_by_id("")

    def test_raises_not_found_for_negative_id(self, service: RecipeService):
        with pytest.raises(RecipeNotFoundError):
            service.get_by_id(-1)

    def test_raises_not_found_for_zero_id(self, service: RecipeService):
        with pytest.raises(RecipeNotFoundError):
            service.get_by_id(0)

    def test_raises_not_found_for_out_of_range_id(self, service: RecipeService):
        with pytest.raises(RecipeNotFoundError):
            service.get_by_id(2**63)

    def test_raises_not_found_for_none_id(self, service: RecipeService):
        with pytest.raises(RecipeNotFoundError):
            service.get_by_id(None)  # type: ignore[arg-type]

    def test_raises_not_found_for_float_id(self, service: RecipeService):
        with pytest.raises(RecipeNotFoundError):
            service.get_by_id(1.5)  # type: ignore[arg-type]

    def test_returns_dto_for_valid_id(self, service: RecipeService):
        recipe_id = service.create(
            RecipeCreateDTO(name="Soup", ingredients="Water, salt")
        )

        result = service.get_by_id(recipe_id)

        assert result.id == recipe_id
        assert result.name == "Soup"
        assert result.ingredients == "Water, salt"


class TestListAll:
    """Verify list_all() ordering per FRS-009."""

    def test_returns_empty_list_when_no_recipes(self, service: RecipeService):
        assert service.list_all() == []

    def test_orders_by_updated_at_desc_then_id_desc(
        self, service: RecipeService, db_session: Session
    ):
        id_one = service.create(
            RecipeCreateDTO(name="First", ingredients="a")
        )
        time.sleep(0.01)
        id_two = service.create(
            RecipeCreateDTO(name="Second", ingredients="b")
        )
        time.sleep(0.01)
        id_three = service.create(
            RecipeCreateDTO(name="Third", ingredients="c")
        )

        results = service.list_all()
        result_ids = [r.id for r in results]

        # Most recently created (and thus most recently updated)
        # should come first.
        assert result_ids == [id_three, id_two, id_one]

    def test_updating_a_recipe_moves_it_to_front(
        self, service: RecipeService
    ):
        id_one = service.create(RecipeCreateDTO(name="First", ingredients="a"))
        time.sleep(0.01)
        id_two = service.create(RecipeCreateDTO(name="Second", ingredients="b"))

        # Touch the older recipe so its updated_at becomes newest.
        time.sleep(0.01)
        service.update(
            id_one, RecipeUpdateDTO(name="First Updated", ingredients="a2")
        )

        results = service.list_all()
        result_ids = [r.id for r in results]

        assert result_ids == [id_one, id_two]
        assert results[0].name == "First Updated"

    def test_stable_tie_break_by_id_desc_when_updated_at_equal(
        self, service: RecipeService, db_session: Session
    ):
        id_one = service.create(RecipeCreateDTO(name="A", ingredients="x"))
        id_two = service.create(RecipeCreateDTO(name="B", ingredients="y"))

        # Force identical updated_at timestamps to verify the id DESC
        # tie-break behaves deterministically.
        recipe_one = db_session.query(Recipe).filter(Recipe.id == id_one).one()
        recipe_two = db_session.query(Recipe).filter(Recipe.id == id_two).one()
        recipe_two.updated_at = recipe_one.updated_at
        db_session.commit()

        results = service.list_all()
        result_ids = [r.id for r in results]

        assert result_ids == [id_two, id_one]

    def test_list_all_returns_recipe_dto_fields(self, service: RecipeService):
        recipe_id = service.create(
            RecipeCreateDTO(name="Pie", ingredients="Apples, sugar")
        )

        results = service.list_all()

        assert len(results) == 1
        dto = results[0]
        assert dto.id == recipe_id
        assert dto.name == "Pie"
        assert dto.ingredients == "Apples, sugar"
        assert dto.created_at is not None
        assert dto.updated_at is not None
