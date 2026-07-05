"""
Minimal SQL migration runner.

Applies .sql files from db/migrations/ in filename order, tracking which
have been applied in the schema_migrations table. Safe to run repeatedly —
already-applied migrations are skipped.

Usage:
    python -m app.db.migrate
"""

import asyncio
import logging
from pathlib import Path

import asyncpg

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "migrations"


async def _ensure_schema_migrations_table(conn: asyncpg.Connection) -> None:
    """
    Creates the schema_migrations tracking table if it doesn't exist yet.
    Runs unconditionally since the runner needs this table before it can
    check which migrations have already been applied.
    """
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT PRIMARY KEY,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


async def run_migrations() -> None:
    settings = get_settings()

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return

    logger.info("Connecting to database to run migrations")
    conn = await asyncpg.connect(dsn=settings.database_url)

    try:
        await _ensure_schema_migrations_table(conn)

        applied_versions = {
            row["version"]
            for row in await conn.fetch("SELECT version FROM schema_migrations")
        }

        for migration_file in migration_files:
            version = migration_file.stem

            if version in applied_versions:
                logger.info("Skipping already-applied migration: %s", version)
                continue

            sql = migration_file.read_text()
            logger.info("Applying migration: %s", version)

            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)",
                    version,
                )

            logger.info("Successfully applied migration: %s", version)

        logger.info("All migrations up to date")

    finally:
        await conn.close()


def main() -> None:
    configure_logging()
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()