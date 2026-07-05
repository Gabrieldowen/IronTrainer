"""
Health check endpoint.

Used by load balancers, container orchestrators (e.g. Render, Kubernetes),
and monitoring tools to verify the service is up and responding.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Returns basic service status. Does not check downstream dependencies
    (DB, Strava, etc.) yet — that will be added once those integrations
    exist, as a separate /health/ready endpoint (readiness vs liveness).
    """
    settings = get_settings()
    logger.debug("Health check requested")
    return HealthResponse(status="ok", environment=settings.app_env)