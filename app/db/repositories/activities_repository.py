"""
Data access for the activities table.

upsert_activity is the core of idempotent webhook processing: calling it
twice with the same strava_activity_id updates the existing row rather
than creating a duplicate.
"""

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def upsert_activity(pool: asyncpg.Pool, *, fields: dict[str, Any]) -> int:
    """
    Inserts a new activity, or updates it if strava_activity_id already
    exists (idempotent — safe to call repeatedly with the same activity).

    `fields` is a dict keyed by column name. Using a dict here (rather than
    ~40 individual keyword args) keeps the calling code in the Strava
    parsing service readable — that service will build this dict directly
    from Strava's API response, field by field, in the next commit.

    Required keys: strava_activity_id, athlete_id, name, activity_type,
    start_date, raw_json. All other keys are optional and default to NULL
    in the database if omitted.

    Returns the row's internal id (our BIGSERIAL primary key, not Strava's).
    """
    columns = [
        "strava_activity_id", "athlete_id", "name", "description",
        "activity_type", "sport_type", "workout_type",
        "distance_meters", "moving_time_seconds", "elapsed_time_seconds",
        "total_elevation_gain_meters", "elev_high_meters", "elev_low_meters",
        "start_date", "start_date_local", "timezone",
        "average_speed_mps", "max_speed_mps", "average_heartrate",
        "max_heartrate", "has_heartrate", "average_cadence",
        "average_watts", "max_watts", "weighted_average_watts",
        "device_watts", "kilojoules", "calories", "suffer_score",
        "perceived_exertion", "start_lat", "start_lng", "end_lat",
        "end_lng", "map_polyline", "gear_id", "achievement_count",
        "kudos_count", "comment_count", "athlete_count", "photo_count",
        "trainer", "commute", "manual", "private", "flagged", "raw_json",
    ]

    required = {"strava_activity_id", "athlete_id", "name", "activity_type", "start_date", "raw_json"}
    missing = required - fields.keys()
    if missing:
        raise ValueError(f"upsert_activity missing required fields: {missing}")

    values = [fields.get(col) for col in columns]
    # raw_json needs explicit JSON serialization; asyncpg doesn't do this
    # implicitly for dict -> jsonb.
    raw_json_index = columns.index("raw_json")
    values[raw_json_index] = json.dumps(values[raw_json_index])

    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
    update_clauses = ", ".join(
        f"{col} = EXCLUDED.{col}" for col in columns if col != "strava_activity_id"
    )

    query = f"""
        INSERT INTO activities ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT (strava_activity_id) DO UPDATE SET
            {update_clauses}
        RETURNING id
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *values)

    activity_id = row["id"]
    logger.info(
        "Upserted activity | id=%d strava_activity_id=%s athlete_id=%s",
        activity_id, fields["strava_activity_id"], fields["athlete_id"],
    )
    return activity_id


async def get_activity_by_strava_id(pool: asyncpg.Pool, strava_activity_id: int) -> asyncpg.Record | None:
    """Fetches a single activity by its Strava ID, or None if not found."""
    query = "SELECT * FROM activities WHERE strava_activity_id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, strava_activity_id)


async def list_activities_for_athlete(pool: asyncpg.Pool, athlete_id: int, limit: int = 50) -> list[asyncpg.Record]:
    """Returns an athlete's activities, most recent first."""
    query = """
        SELECT * FROM activities
        WHERE athlete_id = $1
        ORDER BY start_date DESC
        LIMIT $2
    """
    async with pool.acquire() as conn:
        return await conn.fetch(query, athlete_id, limit)