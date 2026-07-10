"""
Data access for the users table, including Strava OAuth token storage.

This repository is the only place in the codebase that writes SQL
against users.
"""

import logging
from datetime import datetime
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

    Does NOT touch token fields — use update_tokens() for those, so
    a profile refresh never accidentally wipes out valid tokens.
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


async def update_tokens(
    pool: asyncpg.Pool,
    *,
    user_id: int,
    access_token: str,
    refresh_token: str,
    expires_at: datetime,
    scope: str,
) -> None:
    """
    Updates OAuth token fields for an existing user. Called after initial
    connect and after every subsequent token refresh.
    """
    query = """
        UPDATE users
        SET access_token = $2,
            refresh_token = $3,
            token_expires_at = $4,
            token_scope = $5
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        await conn.execute(query, user_id, access_token, refresh_token, expires_at, scope)

    logger.info("Updated tokens for user | user_id=%d", user_id)


async def get_user_by_strava_athlete_id(
    pool: asyncpg.Pool, strava_athlete_id: int
) -> asyncpg.Record | None:
    """Fetches a user (including tokens) by their Strava athlete ID, or None."""
    query = "SELECT * FROM users WHERE strava_athlete_id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, strava_athlete_id)


async def get_user_by_id(pool: asyncpg.Pool, user_id: int) -> asyncpg.Record | None:
    """Fetches a user (including tokens) by internal id — used when refreshing
    an access token ahead of an API call, e.g. during webhook processing."""
    query = "SELECT * FROM users WHERE id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, user_id)


async def get_user_by_discord_id(pool: asyncpg.Pool, discord_id: int) -> asyncpg.Record | None:
    """Fetches a user by their linked Discord id, or None if not connected."""
    query = "SELECT * FROM users WHERE discord_id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, discord_id)


async def link_discord_id(pool: asyncpg.Pool, *, user_id: int, discord_id: int) -> None:
    """
    Associates a Discord user id with an existing users row. Called once
    the Strava OAuth callback completes, using the discord_id passed
    through the OAuth state parameter.
    """
    query = "UPDATE users SET discord_id = $2 WHERE id = $1"
    async with pool.acquire() as conn:
        await conn.execute(query, user_id, discord_id)
    logger.info("Linked Discord account | user_id=%d discord_id=%d", user_id, discord_id)


async def list_users(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Returns all connected users — useful later for admin/debug tooling."""
    query = "SELECT * FROM users ORDER BY created_at ASC"
    async with pool.acquire() as conn:
        return await conn.fetch(query)