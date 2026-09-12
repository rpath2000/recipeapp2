# Database Layer — Recipe Persistence

## Overview
This module defines the persistence layer for the Recipe domain entity,
used by `app.services.recipe_service.RecipeService`.

## Components
- `app/models/base.py` — shared SQLAlchemy declarative `Base`.
- `app/models/recipe.py` — `Recipe` ORM model (`id`, `name`, `ingredients`, `created_at`),
  using a dialect-conditional `GUID` type (PostgreSQL `UUID`, SQLite `CHAR(36)`).
- `app/models/database.py` — engine, `SessionLocal` factory, and `get_db()` FastAPI
  dependency. Reads connection string from `app.db_url.DATABASE_URL`.
- `app/models/__init__.py` — package exports: `Base`, `Recipe`, `get_db`.
- `app/models/migrations/` — Alembic migration tree.
  - `env.py` — supports online/offline mode, reads `DATABASE_URL` only if the
    caller has not already set `sqlalchemy.url`, and preserves existing logger
    configuration (`disable_existing_loggers=False`).
  - `versions/0001_initial_schema.py` — creates the `recipes` table with columns
    matching the ORM model. Uses `postgresql.UUID(as_uuid=False)` on Postgres,
    the same type resolved by the model's `GUID` decorator on that dialect.

## Schema
| Column       | Type                          | Constraints        |
|--------------|-------------------------------|---------------------|
| id           | UUID (Postgres) / CHAR(36)    | Primary Key         |
| name         | VARCHAR(120)                  | NOT NULL            |
| ingredients  | TEXT (max 4000)               | NOT NULL            |
| created_at   | TIMESTAMP WITH TIME ZONE      | NOT NULL            |

## Running Migrations
The deploy runs `alembic upgrade head` against `DATABASE_URL`. The schema
itself is provisioned by a human operator; this migration only creates
tables inside it.

## Rollback
`alembic downgrade -1` (or `base`) drops the `recipes` table.
