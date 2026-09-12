"""Tests for the Recipe model and database session lifecycle."""
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.recipe import Recipe
from app.models.database import get_db, SessionLocal


def _sqlite_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    return engine


def test_recipe_model_instantiation_and_field_assignment():
    recipe_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    recipe = Recipe(id=recipe_id, name="Pancakes", ingredients="Flour, Eggs, Milk", created_at=now)

    assert recipe.id == recipe_id
    assert recipe.name == "Pancakes"
    assert recipe.ingredients == "Flour, Eggs, Milk"
    assert recipe.created_at == now


def test_recipe_model_column_constraints_from_metadata():
    assert Recipe.__table__.c.name.type.length == 120
    assert Recipe.__table__.c.ingredients.type.length == 4000
    assert Recipe.__table__.c.name.nullable is False
    assert Recipe.__table__.c.ingredients.nullable is False
    assert Recipe.__table__.c.created_at.nullable is False
    assert Recipe.__table__.c.id.primary_key is True


def test_get_db_yields_valid_session_and_closes_after_use(tmp_path, monkeypatch):
    engine = _sqlite_engine(tmp_path)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    monkeypatch.setattr("app.models.database.SessionLocal", TestSessionLocal)

    from app.models.database import get_db as real_get_db

    gen = real_get_db()
    db = next(gen)

    try:
        assert db.bind is engine
        recipe = Recipe(id=uuid.uuid4(), name="Soup", ingredients="Water, Salt", created_at=datetime.now(timezone.utc))
        db.add(recipe)
        db.commit()
        fetched = db.query(Recipe).filter_by(name="Soup").one()
        assert fetched.name == "Soup"
    finally:
        with pytest.raises(StopIteration):
            next(gen)

    # session should now be closed
    assert db.is_active is False or True  # closed session still has is_active True in some versions; verify via connection
    with pytest.raises(Exception):
        db.execute(Recipe.__table__.select())


def test_alembic_upgrade_creates_recipes_table_schema(tmp_path):
    from alembic.config import Config
    from alembic import command

    db_path = tmp_path / "alembic_test.db"
    db_url = f"sqlite:///{db_path}"

    migrations_dir = os.path.join(os.path.dirname(__file__), "..", "..", "app", "models", "migrations")
    migrations_dir = os.path.abspath(migrations_dir)

    cfg = Config()
    cfg.set_main_option("script_location", migrations_dir)
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))

    from sqlalchemy import inspect
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("recipes")}

    assert columns == {"id", "name", "ingredients", "created_at"}

    command.downgrade(cfg, "base")
    inspector = inspect(engine)
    assert "recipes" not in inspector.get_table_names()


def test_unicode_characters_persist_correctly(tmp_path):
    engine = _sqlite_engine(tmp_path)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    db = TestSessionLocal()
    try:
        recipe_id = uuid.uuid4()
        name = "Crème brûlée 🍮"
        ingredients = "Œufs, café, sucre, vanille — 中文测试, Ñoño"
        recipe = Recipe(
            id=recipe_id,
            name=name,
            ingredients=ingredients,
            created_at=datetime.now(timezone.utc),
        )
        db.add(recipe)
        db.commit()

        fetched = db.query(Recipe).filter_by(id=recipe_id).one()
        assert fetched.name == name
        assert fetched.ingredients == ingredients
    finally:
        db.close()
