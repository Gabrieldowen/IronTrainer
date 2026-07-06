"""
AI coaching layer: takes an athlete's recent activities and produces a
natural-language training summary via an LLM.

PROVIDER SWAPPING: this uses the OpenAI-compatible client pointed at
whatever LLM_BASE_URL is configured (currently Groq's free API). All
provider-specific details (API key, base URL, model name) come from
Settings — nothing below is hardcoded to Groq. To switch to a different
OpenAI-compatible provider (OpenAI itself, Cerebras, Together AI, etc.),
change LLM_API_KEY / LLM_BASE_URL / LLM_MODEL in .env — no code changes
needed here.

NOTE: this only works for OpenAI-compatible providers. Anthropic's native
API uses a different SDK/request shape entirely — going back to Claude
specifically would mean swapping AsyncOpenAI below for AsyncAnthropic
(see git history, Commit 7 original version, for that implementation).
"""

import logging

import asyncpg
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.db.repositories.activities_repository import list_activities_for_athlete

logger = logging.getLogger(__name__)

COACHING_SYSTEM_PROMPT = (
    "You are an experienced endurance sports coach reviewing an athlete's "
    "recent training log. Give a concise, encouraging, and specific "
    "summary of their training: notable trends (volume, intensity, "
    "consistency), and one or two concrete observations or suggestions. "
    "Keep it to 3-4 short paragraphs. Speak directly to the athlete as "
    "'you'. Do not invent data not present in the activity log."
)


def _format_activities_for_prompt(activities: list[asyncpg.Record]) -> str:
    """
    Converts activity rows into a compact, readable text block for the
    prompt. Deliberately not sending raw_json here — the model doesn't
    need Strava's full payload, just the normalized fields relevant to
    coaching analysis. Keeping this lean also keeps token usage down as
    activity history grows, which matters more on a rate-limited free tier.
    """
    lines = []
    for activity in activities:
        distance_km = (activity["distance_meters"] or 0) / 1000
        duration_min = (activity["moving_time_seconds"] or 0) / 60

        line = (
            f"- {activity['start_date'].strftime('%Y-%m-%d')} | "
            f"{activity['activity_type']} | "
            f"{distance_km:.1f} km | "
            f"{duration_min:.0f} min"
        )
        if activity["average_heartrate"]:
            line += f" | avg HR {activity['average_heartrate']:.0f}"
        if activity["total_elevation_gain_meters"]:
            line += f" | {activity['total_elevation_gain_meters']:.0f}m elevation"
        if activity["suffer_score"]:
            line += f" | suffer score {activity['suffer_score']}"

        lines.append(line)

    return "\n".join(lines)


async def generate_training_summary(pool: asyncpg.Pool, *, user_id: int, athlete_id: int, limit: int = 20) -> str:
    """
    Fetches an athlete's recent activities and generates a natural
    language training summary via the configured LLM provider.

    Raises:
        ValueError: if the athlete has no activities yet.
        openai.APIError (or subclasses): if the LLM API call fails
        (network issue, rate limit, invalid API key, etc.) — left
        unhandled here so the calling route can decide how to respond.
    """
    activities = await list_activities_for_athlete(pool, athlete_id, limit=limit)

    if not activities:
        raise ValueError(f"No activities found for athlete_id={athlete_id}")

    activity_log = _format_activities_for_prompt(activities)
    settings = get_settings()

    # This client construction is the one place provider-specific wiring
    # happens. Swapping LLM_BASE_URL in .env is all that's needed to point
    # this at a different OpenAI-compatible provider.
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    logger.info(
        "Generating training summary | user_id=%d athlete_id=%d activity_count=%d model=%s",
        user_id, athlete_id, len(activities), settings.llm_model,
    )

    response = await client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=1000,
        messages=[
            {"role": "system", "content": COACHING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Here is my training log, most recent first:\n\n{activity_log}",
            },
        ],
    )

    summary_text = response.choices[0].message.content

    logger.info("Generated training summary | user_id=%d", user_id)
    return summary_text