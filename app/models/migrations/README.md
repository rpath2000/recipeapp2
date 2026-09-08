# Migrations

Alembic migration tree for the `recipes` table owned by `app/models`.

## Layout

- `env.py` — Alembic environment; reads `DATABASE_URL` (defaulting to a local
  sqlite file) and imports `Base` from `app.models.database` for autogenerate
  support. Supports both online and offline modes.
- `script.py.mako` — revision template.
- `versions/0001_initial_schema.py` — initial revision creating the `recipes`
  table with the columns and constraints declared on the `Recipe` model.

## Running

The deploy container runs:

alembic upgrade head

using an `alembic.ini` synthesized at deploy time with an absolute
`script_location` pointing at this directory. The schema itself is assumed to
already exist; this migration only creates tables inside it, it never issues
`CREATE DATABASE` or `CREATE SCHEMA`.

## Rollback

alembic downgrade -1

drops the `recipes` table.
