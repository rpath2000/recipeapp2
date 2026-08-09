# app/models — Database Layer

This directory contains the complete SQLAlchemy database layer for the
recipe application: declarative models, engine/session configuration,
Alembic migrations, and health-check utilities.

## Contents

- `database.py` — declarative `Base`, `engine`, `SessionLocal`, `get_db()`
  FastAPI dependency, `init_db()`, and `check_db_health()`.
- `recipe.py` — `Recipe` ORM model (primary domain entity).
- `session.py` — `AuthSession` ORM model backing SSO/session-token
  authentication (`app.security.sso_middleware.SSOMiddleware`).
- `audit_log.py` — `AuditLog` ORM model for traceability of sensitive
  operations.
- `password_reset_token.py` — `PasswordResetToken` ORM model for
  password-reset / verification token flows.
- `migrations/` — Alembic environment and versioned migration scripts.
- `tests/` — automated tests for models, pooling, and migrations.

## Schema Design

### `recipes`

| Column       | Type                     | Constraints                         |
|--------------|--------------------------|--------------------------------------|
| id           | UUID                     | Primary key, default `uuid4()`       |
| name         | VARCHAR(255)             | NOT NULL, indexed (search)           |
| description  | TEXT                     | NOT NULL                             |
| ingredients  | TEXT                     | NOT NULL                             |
| instructions | TEXT                     | NOT NULL                             |
| category     | VARCHAR(100)             | NOT NULL, indexed (filtering)        |
| image_url    | VARCHAR(2048)            | NULLABLE                             |
| created_at   | TIMESTAMPTZ              | NOT NULL, default `now()`            |
| updated_at   | TIMESTAMPTZ              | NOT NULL, default/on-update `now()`  |
| owner_id     | VARCHAR(255)             | NOT NULL, indexed (ownership)        |

Deletes on `recipes` are **hard deletes** — there is no soft-delete flag and
no cascading relationships from `recipes` to other tables, so removing a
recipe permanently removes exactly that row and nothing else.

### `auth_sessions`

Backs session/token-based authentication. Columns: `id` (UUID PK),
`session_token` (unique, indexed), `user_id` (indexed), `created_at`,
`expires_at` (indexed for expiry sweeps), `revoked` (boolean).

### `audit_logs`

Append-only traceability log. Columns: `id` (UUID PK), `actor_id` (indexed),
`action`, `resource_type` + `resource_id` (composite indexed), `details`,
`created_at` (indexed).

### `password_reset_tokens`

Single-use, time-bounded tokens for password reset / verification flows.
Columns: `id` (UUID PK), `token` (unique, indexed), `user_id` (indexed),
`created_at`, `expires_at`, `used` (boolean).

## Timestamp Handling

`created_at` and `updated_at` are populated two ways, layered for defense
in depth:

1. **ORM-level defaults**: `Recipe.created_at`/`updated_at` use Python-side
   `default=`/`onupdate=` callables (`_utcnow`) so every insert/update
   through SQLAlchemy sets these fields automatically, regardless of
   database backend (works identically on SQLite in tests and Postgres in
   production).
2. **Database-level defaults and trigger**: the initial migration sets
   `server_default=now()` on both columns for direct SQL inserts, and
   installs a Postgres trigger (`trg_recipes_set_updated_at` calling
   `set_updated_at()`) that forces `updated_at = now()` on every `UPDATE`
   to `recipes`, so `updated_at` is correct even for updates issued outside
   the ORM.

## Connection Pooling

`database.py` configures a `QueuePool` (for non-SQLite URLs) with:

- `pool_size=15`
- `max_overflow=10`
- `pool_timeout=30s`
- `pool_recycle=1800s`
- `pool_pre_ping=True`

This supports 15 steady-state connections plus a burst of up to 10
additional overflow connections (25 total), comfortably covering the
required 10–20 concurrent sessions without exhaustion. All pool sizing is
overridable via `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, and
`DB_POOL_RECYCLE` environment variables; the connection target itself comes
solely from the shared `DATABASE_URL` environment variable — no
component-local `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`
variables are read here.

## Health Checks

`check_db_health(db: Session | None = None) -> bool` executes a trivial
`SELECT 1` round trip, logs a warning if it exceeds 100ms, and returns
`False` (never raises) on failure. It is re-exported for use by
`app.integrations.db_health.check_db_health` and
`app.integrations.s3_client.S3Client.check_db_health`.

## Migration Workflow

Migrations live under `app/models/migrations/` and are managed with
Alembic.

### Applying migrations

export DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/recipes
alembic -c app/models/migrations/alembic.ini upgrade head

### Rolling back

alembic -c app/models/migrations/alembic.ini downgrade -1

Every migration in this project ships with a corresponding `downgrade()`
that fully reverses its `upgrade()` (dropping indexes before tables,
dropping triggers/functions before dropping the columns/tables they act
on), per the standing rule that all migrations must roll back cleanly.

### Creating a new migration

alembic -c app/models/migrations/alembic.ini revision -m "add_new_field"

Edit the generated file under `app/models/migrations/versions/`, ensuring
both `upgrade()` and `downgrade()` are implemented and symmetric.

### Local/dev bootstrap without Alembic

`init_db()` in `database.py` calls `Base.metadata.create_all()` as a
convenience for local development and test bootstrapping. It is
idempotent and safe to call repeatedly, but it is **not** a substitute for
Alembic migrations in any environment where schema history matters.

## Testing

Run the test suite from the repository root:

pytest app/models/tests

Covered scenarios:

- `test_recipe_model.py` — CRUD round trip with all required fields,
  unique UUID generation, timestamp auto-population on create/update, and
  confirmation that deletes are permanent with no cascading side effects.
- `test_database_pool.py` — concurrent session handling under the
  connection pool and health-check latency.
- `test_migrations.py` — migration script structure and revision chain
  sanity checks.
