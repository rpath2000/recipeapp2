"""Secure outbound connector for persisting recipes via the migrated schema.

This connector wraps writes to the `recipes` table (created by the Alembic
migration in this module) with retry and idempotency semantics. It is used
by callers that need to push a RecipeData payload into the database through
a controlled, resilient path rather than hitting the ORM session directly.

It deliberately does NOT define its own database engine or table: it reuses
the shared session factory from app.models.database and the shared Recipe
model from app.models, and it never opens a connection at import time.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.contracts import RecipeData, ValidationError
from app.models import Recipe

logger = logging.getLogger("app.integrations.connector")

T = TypeVar("T")

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 0.1


class ConnectorError(Exception):
    """Raised when the outbound persistence operation ultimately fails."""


def _with_retry(operation: Callable[[], T], *, operation_name: str) -> T:
    """Execute `operation` with exponential backoff retry on transient errors.

    Only retries on OperationalError (connection drops, deadlocks, etc.),
    which are the transient failures typical of outbound database calls.
    Validation and programming errors are never retried.
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return operation()
        except OperationalError as exc:
            last_error = exc
            logger.warning(
                "transient failure on %s attempt %s/%s: %s",
                operation_name,
                attempt,
                MAX_RETRIES,
                str(exc),
            )
            if attempt < MAX_RETRIES:
                time.sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    logger.error("giving up on %s after %s attempts", operation_name, MAX_RETRIES)
    raise ConnectorError(
        f"{operation_name} failed after {MAX_RETRIES} attempts"
    ) from last_error


def upsert_recipe(db: Session, payload: RecipeData) -> RecipeData:
    """Idempotently persist a RecipeData payload.

    Idempotency key is the recipe's `id` (a UUID chosen by the caller/service
    layer). If a row with that id already exists it is updated in place;
    otherwise a new row is inserted. Calling this twice with the same
    payload produces the same end state and does not create duplicates.

    Raises:
        ValidationError: if the payload fails basic validation rules.
        ConnectorError: if the operation fails after retries.
    """
    _validate_payload(payload)

    def _do_upsert() -> RecipeData:
        existing = db.execute(
            select(Recipe).where(Recipe.id == payload.id)
        ).scalar_one_or_none()

        if existing is not None:
            existing.name = payload.name
            existing.ingredients = payload.ingredients
            existing.created_at = payload.created_at
        else:
            existing = Recipe(
                id=payload.id,
                name=payload.name,
                ingredients=payload.ingredients,
                created_at=payload.created_at,
            )
            db.add(existing)

        db.commit()
        db.refresh(existing)

        return RecipeData(
            id=existing.id,
            name=existing.name,
            ingredients=existing.ingredients,
            created_at=existing.created_at,
        )

    try:
        return _with_retry(_do_upsert, operation_name="upsert_recipe")
    except OperationalError:
        db.rollback()
        raise


def _validate_payload(payload: RecipeData) -> None:
    """Validate the payload before attempting to persist it."""
    if payload.name is None or not payload.name.strip():
        raise ValidationError("Recipe name must not be empty or whitespace-only")
    if len(payload.name) > 120:
        raise ValidationError("Recipe name must not exceed 120 characters")
    if payload.ingredients is None or not payload.ingredients.strip():
        raise ValidationError("Recipe ingredients must not be empty or whitespace-only")
    if len(payload.ingredients) > 4000:
        raise ValidationError("Recipe ingredients must not exceed 4000 characters")
