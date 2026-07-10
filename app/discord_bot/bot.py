"""
Discord bot: account linking and coaching commands.

Runs as a SEPARATE PROCESS from the FastAPI app (see run.py) — it holds
its own persistent connection to Discord and its own DB pool. It shares
the exact same services/repositories as the API, just calls them
in-process rather than over HTTP.
"""

import logging

import discord
from discord.ext import commands

from app.core.config import get_settings
from app.db.repositories.users_repository import get_user_by_discord_id
from app.services.coaching_service import generate_training_summary

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True  # required to read command text in prefix commands

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    logger.info("Discord bot logged in as %s", bot.user)


@bot.command(name="connect")
async def connect_command(ctx: commands.Context) -> None:
    """
    !connect — sends the user a personalized Strava authorization link.

    The link includes their Discord user id as a query param, which
    /strava/connect passes through Strava's OAuth flow as `state`, so the
    callback can link the resulting Strava account back to this Discord user.
    """
    settings = get_settings()
    connect_url = f"{settings.app_base_url}/strava/connect?discord_id={ctx.author.id}"

    await ctx.send(
        f"{ctx.author.mention} Click below to connect your Strava account:\n{connect_url}"
    )
    logger.info("Sent connect link | discord_id=%d", ctx.author.id)


@bot.command(name="summary")
async def summary_command(ctx: commands.Context) -> None:
    """
    !summary — generates and posts an AI training summary for the
    calling user's connected Strava account.
    """
    pool = bot.db_pool  # set in run.py after pool init

    user = await get_user_by_discord_id(pool, ctx.author.id)
    if user is None:
        await ctx.send(
            f"{ctx.author.mention} You haven't connected Strava yet — run `!connect` first."
        )
        return

    await ctx.send(f"{ctx.author.mention} Generating your training summary, one moment...")

    try:
        summary = await generate_training_summary(
            pool, user_id=user["id"], athlete_id=user["strava_athlete_id"]
        )
    except ValueError:
        await ctx.send(f"{ctx.author.mention} No activities found yet — go log a workout!")
        return
    except Exception:
        logger.exception("Failed to generate summary | discord_id=%d", ctx.author.id)
        await ctx.send(
            f"{ctx.author.mention} Something went wrong generating your summary — try again shortly."
        )
        return

    # Discord messages cap at 2000 characters — split if needed rather
    # than silently truncating the model's output.
    if len(summary) <= 2000:
        await ctx.send(summary)
    else:
        for i in range(0, len(summary), 2000):
            await ctx.send(summary[i:i + 2000])