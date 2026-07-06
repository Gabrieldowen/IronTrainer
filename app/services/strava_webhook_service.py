"""
Processes Strava webhook events: fetches the full activity data and
upserts it into the activities table, or handles deletes/athlete events.

This is called AFTER the webhook HTTP response has already been sent
(via FastAPI's BackgroundTasks) — nothing here is on the 2-second clock
Strava enforces for the initial response.
"""

import logging
from datetime import datetime
from typing import Any

import asyncpg

from app.db.repositories.activities_repository import delete_activity_by_strava_id, upsert_activity
from app.db.repositories.strava_events_repository import mark_failed, mark_processed
from app.db.repositories.users_repository import get_user_by_strava_athlete_id
from app.services.strava_activity_service import fetch_activity

logger = logging.getLogger(__name__)


def _parse_strava_datetime(value: str | None) -> datetime | None:
    """
    Parses Strava's ISO 8601 datetime strings (e.g. "2026-07-04T22:56:10Z")
    into timezone-aware datetime objects. asyncpg requires actual datetime
    instances for TIMESTAMPTZ columns — it will not accept a raw string.
    """
    if value is None:
        return None
    # Python's fromisoformat (3.11+) handles the trailing "Z" directly.
    return datetime.fromisoformat(value)


def _map_strava_activity_to_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Maps a raw Strava activity API response to our activities table
    columns. Uses .get() throughout since Strava's response fields vary
    depending on activity type and privacy settings (e.g. non-owners
    don't see heart rate on someone else's private activity).
    """
    start_latlng = raw.get("start_latlng") or [None, None]
    end_latlng = raw.get("end_latlng") or [None, None]
    polyline_map = raw.get("map") or {}

    return {
        "strava_activity_id": raw["id"],
        "athlete_id": raw["athlete"]["id"],
        "name": raw.get("name", "Untitled Activity"),
        "description": raw.get("description"),
        "activity_type": raw.get("type", "Workout"),
        "sport_type": raw.get("sport_type"),
        "workout_type": raw.get("workout_type"),
        "distance_meters": raw.get("distance"),
        "moving_time_seconds": raw.get("moving_time"),
        "elapsed_time_seconds": raw.get("elapsed_time"),
        "total_elevation_gain_meters": raw.get("total_elevation_gain"),
        "elev_high_meters": raw.get("elev_high"),
        "elev_low_meters": raw.get("elev_low"),
        "start_date": _parse_strava_datetime(raw.get("start_date")),
        "start_date_local": _parse_strava_datetime(raw.get("start_date_local")),
        "timezone": raw.get("timezone"),
        "average_speed_mps": raw.get("average_speed"),
        "max_speed_mps": raw.get("max_speed"),
        "average_heartrate": raw.get("average_heartrate"),
        "max_heartrate": raw.get("max_heartrate"),
        "has_heartrate": raw.get("has_heartrate", False),
        "average_cadence": raw.get("average_cadence"),
        "average_watts": raw.get("average_watts"),
        "max_watts": raw.get("max_watts"),
        "weighted_average_watts": raw.get("weighted_average_watts"),
        "device_watts": raw.get("device_watts", False),
        "kilojoules": raw.get("kilojoules"),
        "calories": raw.get("calories"),
        "suffer_score": raw.get("suffer_score"),
        "perceived_exertion": raw.get("perceived_exertion"),
        "start_lat": start_latlng[0],
        "start_lng": start_latlng[1],
        "end_lat": end_latlng[0],
        "end_lng": end_latlng[1],
        "map_polyline": polyline_map.get("summary_polyline"),
        "gear_id": raw.get("gear_id"),
        "achievement_count": raw.get("achievement_count"),
        "kudos_count": raw.get("kudos_count"),
        "comment_count": raw.get("comment_count"),
        "athlete_count": raw.get("athlete_count"),
        "photo_count": raw.get("photo_count"),
        "trainer": raw.get("trainer", False),
        "commute": raw.get("commute", False),
        "manual": raw.get("manual", False),
        "private": raw.get("private", False),
        "flagged": raw.get("flagged", False),
        "raw_json": raw,
    }


async def process_event(pool: asyncpg.Pool, event: asyncpg.Record) -> None:
    """
    Processes a single strava_events row: fetches/upserts the activity
    (for create/update) or removes it (for delete), then marks the event
    processed. Any failure is caught and recorded on the event row rather
    than raised, since this runs in a background task with no caller
    waiting to handle an exception.
    """
    event_id = event["id"]
    object_type = event["object_type"]
    aspect_type = event["aspect_type"]
    object_id = event["object_id"]
    owner_id = event["owner_id"]

    try:
        if object_type != "activity":
            # "athlete" events (e.g. deauthorization) aren't handled yet —
            # log and mark processed so they don't sit in the unprocessed
            # queue forever. Revisit if/when deauthorization handling is needed.
            logger.info(
                "Skipping non-activity event | id=%d object_type=%s", event_id, object_type
            )
            await mark_processed(pool, event_id)
            return

        if aspect_type == "delete":
            await delete_activity_by_strava_id(pool, object_id)
            logger.info("Deleted activity from webhook event | strava_activity_id=%d", object_id)
            await mark_processed(pool, event_id)
            return

        # create or update: fetch the full activity and upsert it
        user = await get_user_by_strava_athlete_id(pool, owner_id)
        if user is None:
            # Event for an athlete who hasn't connected through this app.
            # Not an error — just nothing for us to do.
            logger.warning(
                "No connected user for webhook owner_id=%d, skipping | event_id=%d",
                owner_id, event_id,
            )
            await mark_processed(pool, event_id)
            return

        raw_activity = await fetch_activity(pool, user_id=user["id"], strava_activity_id=object_id)
        fields = _map_strava_activity_to_fields(raw_activity)
        await upsert_activity(pool, fields=fields)

        await mark_processed(pool, event_id)
        logger.info("Successfully processed webhook event | id=%d", event_id)

    except Exception as exc:
        logger.exception("Failed to process webhook event | id=%d", event_id)
        await mark_failed(pool, event_id, error=str(exc))