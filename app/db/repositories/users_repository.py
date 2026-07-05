"""
Data access for the users table.

Users are created during the Strava OAuth connect flow (next commit) —
this repository just provides the lookup/upsert functions that flow and
the webhook processor will both depend on.
"""

import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def upsert_user(
    pool: asyncpg.Pool,
    *,
    strava_athlete_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
    profile_picture_url: str | None = None,
) -> int:
    """
    Creates a user if one doesn't exist for this Strava athlete, or
    updates their profile fields if it does. Returns our internal id.
    """
    query = """
        INSERT INTO users (strava_athlete_id, first_name, last_name, profile_picture_url)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (strava_athlete_id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            profile_picture_url = EXCLUDED.profile_picture_url
        RETURNING id
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            query, strava_athlete_id, first_name, last_name, profile_picture_url
        )

    user_id = row["id"]
    logger.info("Upserted user | id=%d strava_athlete_id=%d", user_id, strava_athlete_id)
    return user_id


async def get_user_by_strava_athlete_id(
    pool: asyncpg.Pool, strava_athlete_id: int
) -> asyncpg.Record | None:
    """Fetches a user by their Strava athlete ID, or None if not connected yet."""
    query = "SELECT * FROM users WHERE strava_athlete_id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, strava_athlete_id)


async def list_users(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Returns all connected users — useful later for admin/debug tooling."""
    query = "SELECT * FROM users ORDER BY created_at ASC"
    async with pool.acquire() as conn:
        return await conn.fetch(query)