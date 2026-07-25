from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from config import Settings, get_settings

# Explicit constraint naming.
#
# Without this, Postgres invents names for indexes, unique constraints and
# foreign keys, and Alembic autogenerate then writes migrations that can create a
# constraint but not drop it, because the downgrade has no name to reference.
# This must be settled before the first migration: changing it later means
# renaming every constraint that already exists.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every model. Models live in models.py."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _engine_kwargs(settings: Settings) -> dict[str, Any]:
    """
    Engine options, which differ behind a transaction-mode pooler.

    A pooler such as Supabase's Supavisor hands out a different backend
    connection per transaction. Two things follow: pooling on our side is
    pointless and holds connections the pooler wants back, and asyncpg's
    prepared-statement cache goes stale — surfacing as
    `prepared statement "__asyncpg_stmt_1__" already exists` under concurrency.
    """
    kwargs: dict[str, Any] = {"echo": settings.db_echo, "pool_pre_ping": True}

    if settings.db_transaction_pooler:
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"statement_cache_size": 0}
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
        kwargs["pool_recycle"] = 1800

    return kwargs


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, **_engine_kwargs(settings))
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            # Attributes stay readable after commit, so a route can return the
            # object it just saved without a lazy reload that would need a live
            # session and fail once the request has ended.
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency giving one session per request.

    Commits when the handler returns, rolls back on any exception.

    Do NOT use this for the SSE endpoint. A streamed response outlives the
    handler that returned it, so the session — and its pooled connection — would
    stay open for the whole generation. Use `session_scope()` there instead.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def session_scope() -> AsyncSession:
    """
    A session for use outside the request/response cycle, caller-managed.

        async with session_scope() as session:
            session.add(message)
            await session.commit()
    """
    return get_session_factory()()


async def check_connection() -> bool:
    """Readiness probe: can we round-trip a query?"""
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    """Close pooled connections. Called from the app's lifespan shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
