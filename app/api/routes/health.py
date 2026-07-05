"""
Health check endpoints.

- /health        Liveness: is the process running at all? No dependencies checked.
- /health/ready  Readiness: can this instance actually serve traffic?
                 Checks downstream dependencies (currently: database).

The liveness/readiness split matters for orchestrators (Render, Kubernetes):
liveness failures trigger a restart, readiness failures just pull the
instance out of the load balancer rotation without restarting it — useful
if the DB has a transient blip and recovers on its own.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import check_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness check. Always returns ok if the process can respond at all."""
    settings = get_settings()
    logger.debug("Liveness check requested")
    return HealthResponse(status="ok", environment=settings.app_env)


@router.get("/health/ready", response_model=ReadinessResponse, status_code=200)
async def readiness_check(response_model=ReadinessResponse):
    """
    Readiness check. Verifies the database is reachable.

    Returns 200 with status="ok" if ready, 503 with status="unavailable"
    if the database check fails — so orchestrators correctly detect this
    instance as not ready for traffic.
    """
    from fastapi import Response
    from fastapi.responses import JSONResponse

    db_ok = await check_db_connection()

    if db_ok:
        return ReadinessResponse(status="ok", database="connected")

    logger.warning("Readiness check failed: database unreachable")
    return JSONResponse(
        status_code=503,
        content=ReadinessResponse(status="unavailable", database="disconnected").model_dump(),
    )