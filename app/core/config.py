"""
Application configuration loaded from environment variables.

Uses pydantic-settings so that:
- All required config is validated at startup (fail fast, not on first request).
- Types are enforced (e.g. PORT must be an int).
- .env files are supported for local development.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application settings.

    Values are read from environment variables first, falling back to a
    .env file if present. See .env.example for the full list of variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10

    # Strava OAuth
    strava_client_id: str
    strava_client_secret: str
    strava_redirect_uri: str

    # Strava Webhooks
    strava_webhook_verify_token: str

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.

    lru_cache ensures we parse environment variables once per process,
    not on every call — settings don't change at runtime.
    """
    return Settings()