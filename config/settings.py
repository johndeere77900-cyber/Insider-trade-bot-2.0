"""
Application configuration for Insider Trade Bot.

This module centralizes environment-based configuration.
Secrets and credentials must never be hard-coded here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# Project root:
# config/settings.py -> config -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration."""

    app_name: str
    environment: str
    database_url: str

    # SEC configuration
    sec_user_agent: str
    sec_base_url: str

    # Storage
    data_directory: Path
    raw_data_directory: Path
    processed_data_directory: Path
    logs_directory: Path

    # Trading safety
    live_trading_enabled: bool
    paper_trading_enabled: bool


def _get_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable safely."""

    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def load_settings() -> Settings:
    """Load application settings from environment variables."""

    data_directory = PROJECT_ROOT / "data"

    settings = Settings(
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
        sec_user_agent=os.getenv(
            "SEC_USER_AGENT",
            "",
        ),
        sec_base_url=os.getenv(
            "SEC_BASE_URL",
            "https://www.sec.gov",
        ),
        data_directory=data_directory,
        raw_data_directory=data_directory / "raw",
        processed_data_directory=data_directory / "processed",
        logs_directory=PROJECT_ROOT / "logs",
        live_trading_enabled=_get_bool(
            "LIVE_TRADING_ENABLED",
            False,
        ),
        paper_trading_enabled=_get_bool(
            "PAPER_TRADING_ENABLED",
            True,
        ),
    )

    return settings


settings = load_settings()
