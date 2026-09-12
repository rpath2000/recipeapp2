"""Integration tests for the recipes migration and the connector/transform seam.

These tests use a dedicated SQLite database file under tmp_path (never the
shared default engine) and drive the actual Alembic migration scripts in
this module against it, then exercise the connector and transform functions
against the resulting schema.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.contracts import RecipeData, ValidationError

from connector import ConnectorError, upsert_recipe
from transform import from_recipe_data, to_recipe_data

MODULE_DIR = Path(__file__).resolve().parent


def _alembic_config(db_url: str) -> Config:
    """Build an Alembic Config pointed at this module's migration scripts
    and at an explicit, test-owned SQLite database URL (never the shared
    default engine or file).
    """
    cfg = Config(str(MODULE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(MODULE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture()
def sqlite_db_url(tmp_path: Path) -> str:
    db_file = tmp_path / "integrations_test.db"
    return f"sqlite:///{db_file}"


def test_alembic_upgrade_head_succeeds_against_empty_database(sqlite_db_url: str) -> None:
    """alembic upgrade head must succeed against a brand new, empty database."""
    cfg = _alembic_config(sqlite_db_url)

    command.upgrade(cfg, "head")

    engine = create_engine(sqlite_db_url)
    inspector = inspect(engine)
    assert "recipes" in inspector.get_table_names()
    engine.dispose()


def test_migration_creates_recipes_table_with_correct_schema(sqlite_db_url: str) -> None:
    """The migration must create a recipes table with the required columns."""
    cfg = _alembic_config(sqlite_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(sqlite_db_url)
    inspector = inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("recipes")}

    assert "id" in columns
    assert "name" in columns
    assert "ingredients" in columns
    assert "created_at" in columns

    pk_constraint = inspector.get_pk_constraint("recipes")
    assert "id" in pk_constraint["constrained_columns"]

    engine.dispose()


def test_alembic_downgrade_base_drops_recipes_table(sqlite_db_url: str) -> None:
    """alembic downgrade base must remove the recipes table entirely."""
    cfg = _alembic_config(sqlite_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(sqlite_db_url)
    inspector = inspect(engine)
    assert "recipes" in inspector.get_table_names()
    engine.dispose()

    command.downgrade(cfg, "base")

    engine = create_engine(sqlite_db_url)
    inspector = inspect(engine)
    assert "recipes" not in inspector.get_table_names()
    engine.dispose()


def test_upsert_recipe_inserts_new_row(sqlite_db_url: str) -> None:
    """upsert_recipe should insert a row when the id does not already exist."""
    cfg = _alembic_config(sqlite_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(sqlite_db_url)
    with Session(engine) as db:
        payload = RecipeData(
            id=uuid.uuid4(),
            name="Pancakes",
            ingredients="flour, milk, eggs",
            created_at=datetime.now(timezone.utc),
        )

        result = upsert_recipe(db, payload)

        assert result.id == payload.id
        assert result.name == "Pancakes"

        row = db.execute(
            text("SELECT name, ingredients FROM recipes WHERE id = :id"),
            {"id": str(payload.id)},
        ).fetchone()
        assert row is not None
        assert row[0] == "Pancakes"
    engine.dispose()


def test_upsert_recipe_is_idempotent_on_same_id(sqlite_db_url: str) -> None:
    """Calling upsert_recipe twice with the same id must update, not duplicate."""
    cfg = _alembic_config(sqlite_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(sqlite_db_url)
    with Session(engine) as db:
        recipe_id = uuid.uuid4()
        first = RecipeData(
            id=recipe_id,
            name="Omelette",
            ingredients="eggs, salt",
            created_at=datetime.now(timezone.utc),
        )
        upsert_recipe(db, first)

        second = RecipeData(
            id=recipe_id,
            name="Omelette Deluxe",
            ingredients="eggs, salt, cheese",
            created_at=datetime.now(timezone.utc),
        )
        result = upsert_recipe(db, second)

        assert result.name == "Omelette Deluxe"

        count = db.execute(
            text("SELECT COUNT(*) FROM recipes WHERE id = :id"),
            {"id": str(recipe_id)},
        ).scalar()
        assert count == 1
    engine.dispose()


def test_upsert_recipe_rejects_empty_name(sqlite_db_url: str) -> None:
    """upsert_recipe must raise ValidationError for a whitespace-only name."""
    cfg = _alembic_config(sqlite_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(sqlite_db_url)
    with Session(engine) as db:
        payload = RecipeData(
            id=uuid.uuid4(),
            name="   ",
            ingredients="eggs",
            created_at=datetime.now(timezone.utc),
        )
        with pytest.raises(ValidationError):
            upsert_recipe(db, payload)
    engine.dispose()


def test_to_recipe_data_transforms_valid_payload() -> None:
    """to_recipe_data should map a raw dict to a RecipeData instance."""
    recipe_id = uuid.uuid4()
    raw = {
        "id": str(recipe_id),
        "name": "Toast",
        "ingredients": "bread",
        "created_at": "2024-01-01T00:00:00+00:00",
    }

    result = to_recipe_data(raw)

    assert result.id == recipe_id
    assert result.name == "Toast"
    assert result.ingredients == "bread"
    assert result.created_at == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_to_recipe_data_rejects_name_over_max_length() -> None:
    """to_recipe_data must raise ValidationError when name exceeds 120 chars."""
    raw = {
        "id": str(uuid.uuid4()),
        "name": "x" * 121,
        "ingredients": "bread",
        "created_at": "2024-01-01T00:00:00+00:00",
    }

    with pytest.raises(ValidationError):
        to_recipe_data(raw)


def test_from_recipe_data_round_trips_through_transform() -> None:
    """from_recipe_data followed by to_recipe_data should preserve data."""
    original = RecipeData(
        id=uuid.uuid4(),
        name="Soup",
        ingredients="water, salt",
        created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    raw = from_recipe_data(original)
    rebuilt = to_recipe_data(raw)

    assert rebuilt.id == original.id
    assert rebuilt.name == original.name
    assert rebuilt.ingredients == original.ingredients
    assert rebuilt.created_at == original.created_at


def test_connector_error_wraps_underlying_failure_message() -> None:
    """ConnectorError should be constructible and carry a descriptive message."""
    error = ConnectorError("upsert_recipe failed after 3 attempts")
    assert "upsert_recipe" in str(error)
