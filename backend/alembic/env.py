import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from config import get_settings
from database import Base

# Importing models registers every table on Base.metadata. Autogenerate only sees
# tables imported by this point, so a missing import here silently produces an
# empty migration.
import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_url() -> str:
    """
    Resolve the connection URL.

    Precedence: `-x db_url=...` on the command line, then the app's
    `migration_url`, which prefers DATABASE_URL_DIRECT. That ordering matters
    against a managed pooler — DDL needs the direct connection, while the
    application itself talks to the pooler.
    """
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    if override:
        return override
    return get_settings().migration_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade head --sql`)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type and default changes, which Alembic ignores by
        # default — without these, altering a column silently produces an empty
        # migration and the drift goes unnoticed.
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations against an async driver.

    The URL uses asyncpg, so Alembic — which is synchronous — has to drive it
    through `run_sync` on an async connection. NullPool because the engine exists
    for exactly one short-lived operation.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
