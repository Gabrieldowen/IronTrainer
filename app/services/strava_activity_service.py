"""
Fetches individual activities from Strava's API and handles access token
refresh transparently.

This is the service the webhook processor calls once it knows *which*
activity to fetch and *which* user (and therefore which token) to fetch
it with.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import httpx

from app.core.config import get_settings
from app.db.repositories.users_repository import get_user_by_id, update_tokens

logger = logging.getLogger(__name__)

STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"

# Refresh a bit before actual expiry, so we don't race a token expiring
# mid-request due to clock skew or request latency.
TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


async def _refresh_access_token(pool: asyncpg.Pool, user: asyncpg.Record) -> str:
    """
    Exchanges a refresh_token for a new access_token, stores the new
    tokens, and returns the fresh access_token.

    Strava's refresh_token is long-lived and typically stays valid across
    refreshes (Strava may or may not rotate it — we store whatever comes
    back either way, per their docs' recommended behavior).
    """
    settings = get_settings()

    payload = {
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": user["refresh_token"],
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(STRAVA_TOKEN_URL, data=payload)
        response.raise_for_status()

    data = response.json()
    expires_at = datetime.fromtimestamp(data["expires_at"], tz=timezone.utc)

    await update_tokens(
        pool,
        user_id=user["id"],
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=expires_at,
        scope=user["token_scope"],  # scope doesn't change on refresh
    )

    logger.info("Refreshed Strava access token | user_id=%d", user["id"])
    return data["access_token"]


async def get_valid_access_token(pool: asyncpg.Pool, user_id: int) -> str:
    """
    Returns a currently-valid access token for the given user, refreshing
    it first if it's expired (or close to it).

    Raises:
        ValueError: if the user doesn't exist or has no tokens stored
        (i.e. never completed the connect flow).
    """
    user = await get_user_by_id(pool, user_id)
    if user is None:
        raise ValueError(f"No user found with id={user_id}")
    if user["access_token"] is None:
        raise ValueError(f"User id={user_id} has not connected a Strava account")

    now = datetime.now(timezone.utc)
    expires_at = user["token_expires_at"]

    if expires_at <= now + TOKEN_REFRESH_BUFFER:
        logger.info("Access token expired or expiring soon | user_id=%d", user_id)
        return await _refresh_access_token(pool, user)

    return user["access_token"]


async def fetch_activity(pool: asyncpg.Pool, *, user_id: int, strava_activity_id: int) -> dict[str, Any]:
    """
    Fetches the full activity object from Strava's API for a given
    activity id, using the given user's (refreshed if needed) access token.

    Raises:
        httpx.HTTPStatusError: if Strava returns a non-2xx response (e.g.
        404 if the activity was deleted between webhook delivery and fetch).
    """
    access_token = await get_valid_access_token(pool, user_id)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/activities/{strava_activity_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()

    return response.json()