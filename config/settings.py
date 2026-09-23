"""
Central configuration for the Insider Trade Bot.

This module contains application configuration and environment-variable
handling. Secrets should be supplied through environment variables rather
than hard-coded into source code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# Project root directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_bool(name: str, default: bool) -> bool:
    """
    Read a boolean environment variable.

    Accepted true values:
        1, true, yes, on

    Everything else is treated as False.
    """
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration."""

    app_name: str
    environment: str

    # Database
    database_url: str

    # SEC
    sec_base_url: str
    sec_user_agent: str

    # Storage directories
    data_directory: Path
    raw_data_directory: Path
    processed_data_directory: Path

    # Logging
    logs_directory: Path

    # Trading safety
    paper_trading_enabled: bool
    live_trading_enabled: bool


def load_settings() -> Settings:
    """
    Load application settings from environment variables.

    Safe defaults are used for development.
    Live trading is disabled by default.
    """

    data_directory = PROJECT_ROOT / "data"

    return Settings(
        app_name=os.getenv(
            "INSIDER_TRADE_BOT_APP_NAME",
            "Insider Trade Bot",
        ),
        environment=os.getenv(
            "INSIDER_TRADE_BOT_ENVIRONMENT",
            "development",
        ),

        database_url=os.getenv(
            "INSIDER_TRADE_BOT_DATABASE_URL",
            f"sqlite:///{data_directory / 'insider_trade_bot.db'}",
        ),

        sec_base_url=os.getenv(
            "SEC_BASE_URL",
            "https://www.sec.gov",
        ),

        sec_user_agent=os.getenv(
            "SEC_USER_AGENT",
            "",
        ),

        data_directory=data_directory,
        raw_data_directory=data_directory / "raw",
        processed_data_directory=data_directory / "processed",

        logs_directory=PROJECT_ROOT / "logs",

        paper_trading_enabled=_get_bool(
            "PAPER_TRADING_ENABLED",
            True,
        ),

        live_trading_enabled=_get_bool(
            "LIVE_TRADING_ENABLED",
            False,
        ),
  )
