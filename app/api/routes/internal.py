"""
Internal/admin maintenance endpoints.

These are not part of the public API surface — they're operational
tools for you (the developer), not for Strava, Discord, or end users.
Protected by a shared-secret header rather than full user auth, since
that doesn't exist yet and would be overkill for this alone.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.repositories.strava_events_repository import get_unprocessed_events
from app.services.strava_webhook_service import process_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_internal_api_key(x_internal_api_key: str = Header(...)) -> None:
    """
    FastAPI dependency that checks the X-Internal-API-Key header against
    our configured secret. Raises 403 if missing or mismatched.
    """
    settings = get_settings()
    if x_internal_api_key != settings.internal_api_key:
        logger.warning("Rejected internal endpoint call: invalid API key")
        raise HTTPException(status_code=403, detail="Invalid internal API key")


class ReplayResult(BaseModel):
    event_id: int
    status: str  # "succeeded" or "failed"
    error: str | None = None


class ReplaySummary(BaseModel):
    total_attempted: int
    succeeded: int
    failed: int
    results: list[ReplayResult]


@router.post("/strava/replay", response_model=ReplaySummary)
async def replay_unprocessed_events(
    request: Request,
    limit: int = 100,
    x_internal_api_key: str = Header(...),
) -> ReplaySummary:
    """
    Re-attempts processing for all strava_events rows with
    processed_at IS NULL (i.e. never successfully processed, whether
    they've never been attempted or previously failed).

    Requires the X-Internal-API-Key header to match INTERNAL_API_KEY.

    Query param `limit` caps how many events to retry in one call
    (default 100), to avoid one request trying to process an unbounded
    backlog and running long.
    """
    _verify_internal_api_key(x_internal_api_key)

    pool = request.app.state.db_pool
    events = await get_unprocessed_events(pool, limit=limit)

    logger.info("Starting replay of %d unprocessed events", len(events))

    results: list[ReplayResult] = []
    for event in events:
        try:
            await process_event(pool, event)
            # process_event marks the event processed/failed internally,
            # so we re-check its outcome rather than assuming success just
            # because no exception escaped (process_event catches its own
            # errors and records them, per its Commit 5 design).
            refreshed = await pool.fetchrow(
                "SELECT processed_at, processing_error FROM strava_events WHERE id = $1",
                event["id"],
            )
            if refreshed["processed_at"] is not None:
                results.append(ReplayResult(event_id=event["id"], status="succeeded"))
            else:
                results.append(
                    ReplayResult(
                        event_id=event["id"],
                        status="failed",
                        error=refreshed["processing_error"],
                    )
                )
        except Exception as exc:
            # Defensive catch — process_event shouldn't raise (it catches
            # its own errors), but if something unexpected escapes it, we
            # don't want one bad event to abort the whole replay batch.
            logger.exception("Unexpected error replaying event | id=%d", event["id"])
            results.append(ReplayResult(event_id=event["id"], status="failed", error=str(exc)))

    succeeded = sum(1 for r in results if r.status == "succeeded")
    failed = len(results) - succeeded

    logger.info(
        "Replay complete | total=%d succeeded=%d failed=%d",
        len(results), succeeded, failed,
    )

    return ReplaySummary(
        total_attempted=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )