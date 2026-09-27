"""
Logging configuration for Insider Trade Bot.

The logging system provides a consistent way for every component of the
agent to record operational events, warnings, errors, and diagnostics.
"""

from __future__ import annotations

import logging
from pathlib import Path


LOGGER_NAME = "insider_trade_bot"


def configure_logging(
    logs_directory: Path | str,
    level: str | int = logging.INFO,
) -> logging.Logger:
    """
    Configure application-wide logging.

    Logs are written to both:
        1. The console
        2. The application log file

    The logging level may be supplied as either a standard logging integer
    or a textual level such as "INFO", "WARNING", or "ERROR".
    """

    logs_directory = Path(
        logs_directory
    )

    logs_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = logging.getLogger(
        LOGGER_NAME
    )

    if isinstance(level, str):
        normalized_level = level.strip().upper()

        resolved_level = getattr(
            logging,
            normalized_level,
            None,
        )

        if not isinstance(
            resolved_level,
            int,
        ):
            raise ValueError(
                f"Invalid logging level: {level}"
            )

        level = resolved_level

    elif not isinstance(level, int):
        raise TypeError(
            "level must be a logging level name or integer."
        )

    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(
        formatter
    )

    file_handler = logging.FileHandler(
        logs_directory
        / "insider_trade_bot.log",
        encoding="utf-8",
    )

    file_handler.setLevel(level)
    file_handler.setFormatter(
        formatter
    )

    logger.addHandler(
        console_handler
    )

    logger.addHandler(
        file_handler
    )

    logger.propagate = False

    return logger


def get_logger(
    name: str | None = None,
) -> logging.Logger:
    """
    Return a logger for the application.

    If a component name is supplied, it becomes a child logger of the
    main Insider Trade Bot logger.
    """

    if name:
        return logging.getLogger(
            f"{LOGGER_NAME}.{name}"
        )

    return logging.getLogger(
        LOGGER_NAME
        )
