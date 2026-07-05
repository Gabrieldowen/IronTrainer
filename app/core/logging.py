"""
Logging configuration for the application.

We configure the root logger once at startup. All modules should use
`logging.getLogger(__name__)` to get a logger scoped to their module path,
which makes it easy to filter/search logs by origin.
"""

import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    """
    Configures the root logger with a consistent format across the app.

    Format includes timestamp, level, logger name (module path), and message.
    This is deliberately plain-text (not JSON) for now — we can swap the
    formatter for a JSON one later without touching call sites, since all
    modules log through the standard `logging` interface.
    """
    settings = get_settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if configure_logging() is called more than once
    # (e.g. in tests that re-import the app).
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet down noisy third-party loggers unless we're debugging.
    if log_level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)