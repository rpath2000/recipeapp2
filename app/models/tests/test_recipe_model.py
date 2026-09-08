import time
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, Recipe, get_db, SessionLocal


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    event.listen(eng, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db_session(engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_recipe_maps_to_recipes_table():
    assert Recipe.__tablename__ == "recipes"
    columns = Recipe.__table__.c
    assert "id" in columns
    assert "name" in columns
    assert "ingredients" in columns
    assert "created_at" in columns
    assert "updated_at" in columns


def test_recipe_column_length_constraints():
    assert Recipe.__table__.c.name.type.length == 120
    assert Recipe.__table__.c.name.nullable is False
    assert Recipe.__table__.c.ingredients.nullable is False


def test_recipe_fields_accessible(db_session):
    recipe = Recipe(name="Pancakes", ingredients="flour, eggs, milk")
    db_session.add(recipe)
    db_session.commit()

    fetched = db_session.query(Recipe).first()
    assert fetched.id is not None
    assert fetched.name == "Pancakes"
    assert fetched.ingredients == "flour, eggs, milk"
    assert isinstance(fetched.created_at, datetime)
    assert isinstance(fetched.updated_at, datetime)


def test_insert_populates_timestamps(db_session):
    recipe = Recipe(name="Soup", ingredients="water, salt")
    db_session.add(recipe)
    db_session.commit()

    assert recipe.created_at is not None
    assert recipe.updated_at is not None


def test_update_refreshes_updated_at_leaves_created_at(db_session):
    recipe = Recipe(name="Salad", ingredients="lettuce, tomato")
    db_session.add(recipe)
    db_session.commit()

    original_created_at = recipe.created_at
    original_updated_at = recipe.updated_at

    time.sleep(1.1)

    recipe.ingredients = "lettuce, tomato, cucumber"
    db_session.commit()
    db_session.refresh(recipe)

    assert recipe.created_at == original_created_at
    assert recipe.updated_at > original_updated_at


def test_get_db_yields_session_and_closes():
    gen = get_db()
    session = next(gen)
    assert session is not None

    closed = {"value": False}
    original_close = session.close

    def tracking_close():
        closed["value"] = True
        original_close()

    session.close = tracking_close

    with pytest.raises(StopIteration):
        next(gen)

    assert closed["value"] is True
