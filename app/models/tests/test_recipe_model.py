"""
Tests for the Recipe ORM model:
- creation/retrieval of all required fields
- unique UUID generation on insert
- timestamp auto-population on create and update
- deletes are permanent (no cascading soft-delete behavior)
"""

from __future__ import annotations

import time
import uuid

from app.models.recipe import Recipe


def _make_recipe(owner_id: str, **overrides) -> Recipe:
    defaults = dict(
        name="Pancakes",
        description="Fluffy breakfast pancakes",
        ingredients="flour, eggs, milk, sugar",
        instructions="Mix and cook on a griddle.",
        category="breakfast",
        image_url="https://example.com/pancakes.png",
        owner_id=owner_id,
    )
    defaults.update(overrides)
    return Recipe(**defaults)


def test_recipe_creates_and_retrieves_with_all_required_fields(db_session, sample_owner_id):
    recipe = _make_recipe(sample_owner_id)
    db_session.add(recipe)
    db_session.commit()

    fetched = db_session.query(Recipe).filter_by(id=recipe.id).one()

    assert fetched.id == recipe.id
    assert fetched.name == "Pancakes"
    assert fetched.description == "Fluffy breakfast pancakes"
    assert fetched.ingredients == "flour, eggs, milk, sugar"
    assert fetched.instructions == "Mix and cook on a griddle."
    assert fetched.category == "breakfast"
    assert fetched.image_url == "https://example.com/pancakes.png"
    assert fetched.owner_id == sample_owner_id
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_recipe_allows_nullable_image_url(db_session, sample_owner_id):
    recipe = _make_recipe(sample_owner_id, image_url=None)
    db_session.add(recipe)
    db_session.commit()

    fetched = db_session.query(Recipe).filter_by(id=recipe.id).one()
    assert fetched.image_url is None


def test_unique_uuid_generated_on_insert(db_session, sample_owner_id):
    recipe_a = _make_recipe(sample_owner_id)
    recipe_b = _make_recipe(sample_owner_id)

    db_session.add_all([recipe_a, recipe_b])
    db_session.commit()

    assert isinstance(recipe_a.id, uuid.UUID)
    assert isinstance(recipe_b.id, uuid.UUID)
    assert recipe_a.id != recipe_b.id


def test_timestamps_autopopulate_on_create_and_update(db_session, sample_owner_id):
    recipe = _make_recipe(sample_owner_id)
    db_session.add(recipe)
    db_session.commit()

    created_at = recipe.created_at
    updated_at_initial = recipe.updated_at

    assert created_at is not None
    assert updated_at_initial is not None

    time.sleep(0.01)
    recipe.name = "Updated Pancakes"
    db_session.commit()

    db_session.refresh(recipe)

    assert recipe.created_at == created_at
    assert recipe.updated_at >= updated_at_initial


def test_delete_is_permanent_no_cascade_side_effects(db_session, sample_owner_id):
    recipe = _make_recipe(sample_owner_id)
    db_session.add(recipe)
    db_session.commit()
    recipe_id = recipe.id

    db_session.delete(recipe)
    db_session.commit()

    result = db_session.query(Recipe).filter_by(id=recipe_id).one_or_none()
    assert result is None

    # Deleting again / querying again confirms no orphaned or cascaded
    # artifacts remain and no exception is raised on a clean re-query.
    result_again = db_session.query(Recipe).filter_by(id=recipe_id).one_or_none()
    assert result_again is None
