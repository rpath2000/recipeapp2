"""Alembic environment configuration for database migrations.

Reads DATABASE_URL from the shared app.db_url module (which itself honors
the DATABASE_URL environment variable) and imports the shared declarative
Base/metadata from app.models so autogenerate and migrations stay in sync
with the ORM models owned by app.models.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the repository root is importable when Alembic is invoked from any
# working directory (e.g. `alembic upgrade head` run from app/integrations).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db_url import DATABASE_URL  # noqa: E402
from app.models import Base  # noqa: E402

# Alembic Config object, providing access to values in alembic.ini.
config = context.config

# Interpret the config file for Python logging, if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata used for 'autogenerate' support.
target_metadata = Base.metadata

# Override the sqlalchemy.url from alembic.ini with the shared DATABASE_URL
# so there is a single source of truth for the connection string.
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an
    Engine is acceptable here as well. By skipping the Engine creation we
    don't even need a DBAPI to be available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a connection
    with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
