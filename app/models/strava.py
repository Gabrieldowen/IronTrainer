"""
Pydantic models for Strava API request/response shapes.
"""

from pydantic import BaseModel


class StravaAthleteSummary(BaseModel):
    id: int
    firstname: str | None = None
    lastname: str | None = None
    profile: str | None = None


class StravaTokenExchangeResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int
    expires_in: int
    token_type: str
    scope: str | None = None
    athlete: StravaAthleteSummary | None = None