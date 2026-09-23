"""
Logging configuration for Insider Trade Bot.

The logging system provides a consistent way for every component of the
agent to record operational events, warnings, errors, and diagnostics.
"""

from __future__ import annotations

import logging
from pathlib import Path


LOGGER_NAME = "insider_trade_bot"


def configure_logging(logs_directory: Path) -> logging.Logger:
    """
    Configure application-wide logging.

    Logs are written to both:
        1. The console
        2. The application log file
    """

    logs_directory = Path(logs_directory)
    logs_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = logging.getLogger(LOGGER_NAME)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(
        logs_directory / "insider_trade_bot.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.propagate = False

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Return a logger for the application.

    If a component name is supplied, it becomes a child logger of the
    main Insider Trade Bot logger.
    """

    if name:
        return logging.getLogger(
            f"{LOGGER_NAME}.{name}"
        )

    return logging.getLogger(LOGGER_NAME)
