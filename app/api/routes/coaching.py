"""
AI coaching routes.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.db.repositories.activities_repository import list_activities_for_athlete
from app.db.repositories.users_repository import get_user_by_id
from app.models.coaching import CoachingSummaryResponse
from app.services.coaching_service import generate_training_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["coaching"])


@router.get("/{user_id}/coaching/summary", response_model=CoachingSummaryResponse)
async def get_coaching_summary(user_id: int, request: Request, limit: int = 20) -> CoachingSummaryResponse:
    """
    Generates an AI training summary for a user's recent activities.

    `limit` controls how many recent activities are included (default 20).
    """
    pool = request.app.state.db_pool

    user = await get_user_by_id(pool, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"No user found with id={user_id}")

    try:
        summary = await generate_training_summary(
            pool,
            user_id=user_id,
            athlete_id=user["strava_athlete_id"],
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("Failed to generate coaching summary | user_id=%d", user_id)
        raise HTTPException(status_code=502, detail="Failed to generate coaching summary")

    activities = await list_activities_for_athlete(pool, user["strava_athlete_id"], limit=limit)

    return CoachingSummaryResponse(
        user_id=user_id,
        activity_count=len(activities),
        summary=summary,
    )