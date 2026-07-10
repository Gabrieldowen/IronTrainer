"""
Entrypoint for running the Discord bot as its own process.

Usage:
    python -m app.discord_bot.run
"""

import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import close_db_pool, init_db_pool
from app.discord_bot.bot import bot

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    settings = get_settings()

    pool = await init_db_pool()
    bot.db_pool = pool  # attached here so command handlers in bot.py can reach it

    try:
        logger.info("Starting Discord bot")
        await bot.start(settings.discord_bot_token)
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())