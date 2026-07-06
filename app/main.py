"""
FastAPI application entrypoint.

Uses an application factory (`create_app`) rather than a module-level
`app = FastAPI()` singleton, so tests can create isolated app instances
and so startup/shutdown logic is explicit and testable.
"""

import logging

from fastapi import FastAPI

from app.api.routes import health, strava
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import close_db_pool, init_db_pool

configure_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AI Endurance Coach API",
        description="Backend for AI-powered endurance training analysis and coaching.",
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    app.include_router(health.router)
    app.include_router(strava.router)

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info(
            "Application starting | env=%s | log_level=%s",
            settings.app_env,
            settings.log_level,
        )
        app.state.db_pool = await init_db_pool()
        
    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("Application shutting down")
        await close_db_pool()

    return app


app = create_app()