"""
Data access for the strava_events table.

This is the only place in the codebase that writes SQL against
strava_events. Services call these functions rather than touching asyncpg
directly.
"""

import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def insert_event(
    pool: asyncpg.Pool,
    *,
    object_type: str,
    aspect_type: str,
    object_id: int,
    owner_id: int,
    raw_payload: dict[str, Any],
) -> int:
    """
    Inserts a raw webhook event. Called BEFORE any processing so every
    delivery is durably recorded first, even if processing later fails.

    Returns the new row's id, used to mark the event processed/failed
    once handling completes.
    """
    query = """
        INSERT INTO strava_events (object_type, aspect_type, object_id, owner_id, raw_payload)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        RETURNING id
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            query, object_type, aspect_type, object_id, owner_id, json.dumps(raw_payload)
        )

    event_id = row["id"]
    logger.info(
        "Recorded strava_event | id=%d object_type=%s aspect_type=%s object_id=%d",
        event_id, object_type, aspect_type, object_id,
    )
    return event_id


async def mark_processed(pool: asyncpg.Pool, event_id: int) -> None:
    """Marks an event as successfully processed."""
    query = "UPDATE strava_events SET processed_at = now(), processing_error = NULL WHERE id = $1"
    async with pool.acquire() as conn:
        await conn.execute(query, event_id)
    logger.info("Marked strava_event as processed | id=%d", event_id)


async def mark_failed(pool: asyncpg.Pool, event_id: int, error: str) -> None:
    """
    Records a processing failure without raising further. processed_at
    stays NULL, so the event remains visible to a future replay job.
    """
    query = "UPDATE strava_events SET processing_error = $2 WHERE id = $1"
    async with pool.acquire() as conn:
        await conn.execute(query, event_id, error)
    logger.error("Marked strava_event as failed | id=%d error=%s", event_id, error)


async def get_unprocessed_events(pool: asyncpg.Pool, limit: int = 100) -> list[asyncpg.Record]:
    """Returns unprocessed events, oldest first — used by a future replay job."""
    query = """
        SELECT id, object_type, aspect_type, object_id, owner_id,
               raw_payload, received_at, processing_error
        FROM strava_events
        WHERE processed_at IS NULL
        ORDER BY received_at ASC
        LIMIT $1
    """
    async with pool.acquire() as conn:
        return await conn.fetch(query, limit)