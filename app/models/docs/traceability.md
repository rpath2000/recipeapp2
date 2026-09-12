# Requirements Traceability — Database Task

| Requirement                                                                 | Implementation                                                        |
|-------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| Recipe model with id (UUID), name (String 120), ingredients (Text 4000), created_at (DateTime tz) | `app/models/recipe.py` — `Recipe` class                                |
| Declarative Base                                                              | `app/models/base.py`, re-exported via `app/models/__init__.py`         |
| Database session factory and `get_db` dependency reading `DATABASE_URL`       | `app/models/database.py`                                              |
| Alembic migration creating recipes table with UTF-8 encoding                  | `app/models/migrations/versions/0001_initial_schema.py`, UTF-8 handled natively by TEXT/VARCHAR in Postgres |
| `get_db` yields a session and closes it after request                        | `app/models/database.py::get_db` (try/finally close), tested in `tests/models/test_recipe_database.py` |
| Alembic migration creates schema matching Recipe model                       | Tested via `test_alembic_upgrade_creates_recipes_table_schema`         |
| Unicode persists correctly                                                    | Tested via `test_unicode_characters_persist_correctly`                 |
| `DATABASE_URL` read for connection string                                    | `app/db_url.py` import in `app/models/database.py` and `env.py`        |

## Test Coverage
- `tests/models/test_recipe_database.py`:
  - Recipe model instantiation and field assignment
  - Metadata-level constraint assertions (column lengths, nullability, PK)
  - `get_db` session lifecycle (yield + close)
  - Alembic upgrade/downgrade schema verification
  - Unicode persistence in `name` and `ingredients`
