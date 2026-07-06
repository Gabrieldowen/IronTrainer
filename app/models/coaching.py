"""
Pydantic models for the AI coaching summary feature.
"""

from pydantic import BaseModel


class CoachingSummaryResponse(BaseModel):
    user_id: int
    activity_count: int
    summary: str