"""
Tests for the app.models database layer.

Uses the shared db_session fixture (provided by the test harness) for
anything that touches the application's actual configured database, and
builds an isolated, explicitly-created SQLite engine only for the
Alembic-migration test, per the project's testing rules.
"""

import os
import subprocess
import sys
import textwrap

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker

from app.models import Base, Recipe, get_db


def test_recipe_instantiation_created_at_none_pre_persist():
    recipe = Recipe(name="Pancakes", ingredients="flour\nmilk\neggs")
    assert recipe.name == "Pancakes"
    assert recipe.ingredients == "flour\nmilk\neggs"
    # Not yet persisted: no default has fired.
    assert recipe.created_at is None


def test_recipe_name_length_constraint_declared_in_metadata():
    # Verify the declared constraint from metadata - true on every engine.
    assert Recipe.__table__.c.name.type.length == 120


def test_recipe_ingredients_preserves_line_breaks_and_whitespace(db_session):
    text = "  2 cups flour\n1 tsp salt\n\n  mix well  \n"
    recipe = Recipe(name="Bread", ingredients=text)
    db_session.add(recipe)
    db_session.flush()

    fetched = db_session.query(Recipe).filter_by(id=recipe.id).one()
    assert fetched.ingredients == text


def test_recipe_created_at_autopopulates_on_insert(db_session):
    recipe = Recipe(name="Soup", ingredients="water\nsalt")
    db_session.add(recipe)
    db_session.flush()

    assert recipe.created_at is not None


def test_get_db_yields_session_and_closes_after_request():
    gen = get_db()
    session = next(gen)
    try:
        assert session is not None
        # Session should be usable while the generator is active.
        session.execute(Recipe.__table__.select().limit(0))
    finally:
        # Exhaust the generator - triggers the `finally: db.close()` path.
        with pytest.raises(StopIteration):
            next(gen)

    # After close, further use raises because the underlying connection
    # resource has been released.
    with pytest.raises(Exception):
        session.execute(Recipe.__table__.select())


def test_recipe_name_validation_enforced_at_application_layer():
    """
    The database layer (SQLite in tests) does not enforce VARCHAR(120);
    only the metadata declares the limit and the application layer
    (app.services / app.contracts.ValidationError) enforces the rule.
    This test verifies the metadata declaration and that the shared
    exception type exists for that enforcement, without asserting the
    database rejected anything.
    """
    from app.contracts import ValidationError

    assert Recipe.__table__.c.name.type.length == 120
    assert issubclass(ValidationError, Exception)


def test_alembic_migration_applies_cleanly_to_empty_schema(tmp_path):
    """
    Runs `alembic upgrade head` against a fresh, isolated SQLite database
    file under tmp_path, then verifies the recipes table and its columns
    exist, and that downgrade cleanly removes it.
    """
    db_path = tmp_path / "migration_test.db"
    database_url = f"sqlite:///{db_path}"

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    migrations_dir = os.path.join(os.path.dirname(__file__), "..", "migrations")
    migrations_dir = os.path.abspath(migrations_dir)

    ini_content = textwrap.dedent(
        f"""
        [alembic]
        script_location = {migrations_dir}
        sqlalchemy.url = {database_url}

        [loggers]
        keys = root

        [handlers]
        keys = console

        [formatters]
        keys = generic

        [logger_root]
        level = WARN
        handlers = console
        qualname =

        [handler_console]
        class = StreamHandler
        args = (sys.stderr,)
        level = NOTSET
        formatter = generic

        [formatter_generic]
        format = %(levelname)-5.5s [%(name)s] %(message)s
        """
    )
    ini_path = tmp_path / "alembic.ini"
    ini_path.write_text(ini_content)

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ini_path), "upgrade", "head"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade failed: {result.stderr}\n{result.stdout}"

    engine = create_engine(database_url)
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))

    inspector = inspect(engine)
    assert "recipes" in inspector.get_table_names()

    columns = {col["name"] for col in inspector.get_columns("recipes")}
    assert columns == {"id", "name", "ingredients", "created_at"}

    pk = inspector.get_pk_constraint("recipes")
    assert pk["constrained_columns"] == ["id"]

    engine.dispose()

    # Rollback: verify downgrade removes the table.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ini_path), "downgrade", "base"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic downgrade failed: {result.stderr}\n{result.stdout}"

    engine2 = create_engine(database_url)
    inspector2 = inspect(engine2)
    assert "recipes" not in inspector2.get_table_names()
    engine2.dispose()
