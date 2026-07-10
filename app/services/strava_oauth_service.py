"""
Business logic for the Strava OAuth connect flow.

Handles the authorization URL construction and the authorization-code-for-
token exchange. Routes call into this service and stay thin; this service
has no FastAPI imports, so it's testable in isolation and reusable if we
ever add another entrypoint (e.g. a CLI connect command or a Discord bot
command in a later commit).
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import asyncpg
import httpx

from app.core.config import get_settings
from app.db.repositories.users_repository import link_discord_id, update_tokens, upsert_user
from app.models.strava import StravaTokenExchangeResponse

logger = logging.getLogger(__name__)

STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"

# Scopes needed: read basic profile, and read all activities (including
# private ones the athlete has marked private, since we want a complete
# training log for coaching purposes).
STRAVA_OAUTH_SCOPE = "read,activity:read_all"


def build_authorization_url(state: str | None = None) -> str:
    """
    Constructs the URL to redirect a user to for Strava's authorization
    consent screen. After the user approves, Strava redirects back to our
    STRAVA_REDIRECT_URI with a `code` query param (and `state`, unchanged,
    if we sent one).

    `state` is used to carry the Discord user id through the OAuth round
    trip, so the callback knows which Discord account to link once the
    exchange completes. Strava treats `state` as an opaque passthrough
    value — it doesn't inspect or validate it.
    """
    settings = get_settings()

    params = {
        "client_id": settings.strava_client_id,
        "redirect_uri": settings.strava_redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": STRAVA_OAUTH_SCOPE,
    }
    if state is not None:
        params["state"] = state

    return f"{STRAVA_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> StravaTokenExchangeResponse:
    """
    Exchanges the authorization code (from Strava's callback redirect) for
    access and refresh tokens.

    Raises:
        httpx.HTTPStatusError: if Strava rejects the request (e.g. the code
        is invalid, expired, or already used — codes are single-use).
    """
    settings = get_settings()

    payload = {
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "code": code,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(STRAVA_TOKEN_URL, data=payload)
        response.raise_for_status()

    return StravaTokenExchangeResponse.model_validate(response.json())


async def complete_connect_flow(pool: asyncpg.Pool, code: str, discord_id: int | None = None) -> int:
    """
    Full connect flow: exchanges the code for tokens, creates/updates the
    user record from the athlete profile Strava returns, stores the
    tokens, and (if provided) links the Discord account that initiated
    this connect flow. Returns our internal user id.

    This is idempotent — if the same athlete connects again (e.g.
    re-authorizing after revoking access), their existing user row is
    updated in place rather than duplicated.
    """
    token_response = await exchange_code_for_tokens(code)

    if token_response.athlete is None:
        raise ValueError("Strava token exchange response did not include athlete data")

    user_id = await upsert_user(
        pool,
        strava_athlete_id=token_response.athlete.id,
        first_name=token_response.athlete.firstname,
        last_name=token_response.athlete.lastname,
        profile_picture_url=token_response.athlete.profile,
    )

    expires_at = datetime.fromtimestamp(token_response.expires_at, tz=timezone.utc)

    await update_tokens(
        pool,
        user_id=user_id,
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        expires_at=expires_at,
        scope=token_response.scope or STRAVA_OAUTH_SCOPE,
    )

    if discord_id is not None:
        await link_discord_id(pool, user_id=user_id, discord_id=discord_id)

    logger.info(
        "Completed Strava connect flow | user_id=%d strava_athlete_id=%d discord_id=%s",
        user_id, token_response.athlete.id, discord_id,
    )
    return user_id