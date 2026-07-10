"""
Strava OAuth connect flow and webhook receiver routes.

GET  /strava/connect   -> redirects the user to Strava's consent screen
GET  /strava/callback  -> Strava redirects back here with a `code`,
                           which we exchange for tokens
GET  /strava/webhook   -> handshake verification when registering the
                           webhook subscription (one-time, done manually)
POST /strava/webhook   -> actual event delivery from Strava
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.repositories.strava_events_repository import insert_event
from app.services.strava_oauth_service import build_authorization_url, complete_connect_flow
from app.services.strava_webhook_service import process_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strava", tags=["strava"])

class ConnectSuccessResponse(BaseModel):
    status: str
    user_id: int


@router.get("/connect")
async def connect(discord_id: int | None = Query(default=None)) -> RedirectResponse:
    """
    Redirects the user to Strava's authorization consent screen.

    If discord_id is provided (as it will be when the bot sends this
    link), it's passed through as Strava's OAuth `state` param, so the
    callback can link the resulting Strava account to that Discord user.
    """
    state = str(discord_id) if discord_id is not None else None
    auth_url = build_authorization_url(state=state)
    logger.info("Redirecting user to Strava authorization page | discord_id=%s", discord_id)
    return RedirectResponse(url=auth_url)

@router.get("/callback", response_model=ConnectSuccessResponse)
async def callback(
    request: Request,
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> ConnectSuccessResponse:
    """
    Strava redirects here after the user approves (or denies) access.

    - On approval: `code` is present, we exchange it for tokens.
    - On denial: `error=access_denied` is present instead, no `code`.
    - `state` carries back the discord_id we sent in /connect, unchanged,
      if this flow was initiated from Discord.
    """
    if error:
        logger.warning("Strava authorization denied by user | error=%s", error)
        raise HTTPException(status_code=400, detail=f"Strava authorization failed: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' query parameter")

    pool = request.app.state.db_pool
    discord_id = int(state) if state else None

    try:
        user_id = await complete_connect_flow(pool, code, discord_id=discord_id)
    except Exception:
        logger.exception("Failed to complete Strava connect flow")
        raise HTTPException(status_code=502, detail="Failed to connect Strava account")

    return ConnectSuccessResponse(status="connected", user_id=user_id)



@router.get("/webhook")
async def webhook_handshake(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> dict[str, str]:
    """
    Handshake verification, sent by Strava ONCE when you register a
    webhook subscription (not sent on every event). Must echo back
    hub_challenge if hub_verify_token matches our configured secret.
    """
    settings = get_settings()

    if hub_mode != "subscribe" or hub_verify_token != settings.strava_webhook_verify_token:
        logger.warning("Webhook handshake failed verification")
        raise HTTPException(status_code=403, detail="Verification token mismatch")

    logger.info("Webhook handshake verified successfully")
    return {"hub.challenge": hub_challenge}


@router.post("/webhook", status_code=200)
async def webhook_event(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """
    Receives an actual webhook event delivery from Strava.

    Per Strava's requirements, this must respond within 2 seconds. We do
    the minimum possible work synchronously (record the raw event) and
    defer actual processing (fetching + upserting the activity) to a
    background task that runs after the response is sent.
    """
    payload: dict[str, Any] = await request.json()
    pool = request.app.state.db_pool

    event_id = await insert_event(
        pool,
        object_type=payload["object_type"],
        aspect_type=payload["aspect_type"],
        object_id=payload["object_id"],
        owner_id=payload["owner_id"],
        raw_payload=payload,
    )

    async def _process():
        event = await pool.fetchrow("SELECT * FROM strava_events WHERE id = $1", event_id)
        await process_event(pool, event)

    background_tasks.add_task(_process)

    # Strava only cares that we returned 200 — body content doesn't matter.
    return {"status": "received"}