"""
Database connection pool management.

The pool is created once at application startup and reused across all
requests. FastAPI dependency `get_db_pool` gives route/service code access
to it without importing this module's internals directly.
"""

import logging

import asyncpg

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Module-level reference to the pool. Set during app startup, cleared on
# shutdown. Not accessed directly outside this module — use get_db_pool().
_pool: asyncpg.Pool | None = None


async def init_db_pool() -> asyncpg.Pool:
    """
    Creates the asyncpg connection pool. Called once during app startup.

    Raises:
        asyncpg.PostgresError subclasses if the database is unreachable or
        credentials are invalid — this will crash startup, which is the
        desired behavior (fail fast rather than serve traffic with no DB).
    """
    global _pool

    settings = get_settings()

    logger.info(
        "Creating database connection pool | min_size=%d max_size=%d",
        settings.db_pool_min_size,
        settings.db_pool_max_size,
    )

    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        command_timeout=30,
        statement_cache_size=0,
    )

    logger.info("Database connection pool created successfully")
    return _pool


async def close_db_pool() -> None:
    """Closes the connection pool gracefully. Called during app shutdown."""
    global _pool

    if _pool is not None:
        logger.info("Closing database connection pool")
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """
    Returns the active connection pool.

    Raises:
        RuntimeError: if called before init_db_pool() has run. This is a
        programming error (route wired up before startup completed), not
        something that should ever happen in a running app — it's a signal
        that startup wiring is broken.
    """
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized. init_db_pool() must be called "
            "during application startup before get_pool() is used."
        )
    return _pool


async def check_db_connection() -> bool:
    """
    Verifies the database is reachable by running a trivial query.

    Used by the /health/ready endpoint. Returns False rather than raising,
    since a failed readiness check is an expected, handled condition (the
    orchestrator should stop routing traffic here), not a crash.
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        logger.exception("Database readiness check failed")
        return False