"""
Application configuration model.

Collects high-level runtime settings without replacing the lower-level
configuration already defined in config/settings.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationConfiguration:
    """High-level configuration for the application runtime."""

    environment: str = "development"
    paper_trading_enabled: bool = True
    live_trading_enabled: bool = False
    telegram_enabled: bool = False
    historical_data_available: bool = False
    strict_mode: bool = True

    def validate(self) -> None:
        """Validate configuration safety constraints."""

        environment = self.environment.strip().lower()

        if not environment:
            raise ValueError("environment is required.")

        if self.live_trading_enabled and environment == "development":
            raise ValueError(
                "Live trading cannot be enabled in development environment."
            )

        if self.live_trading_enabled and not self.strict_mode:
            raise ValueError(
                "Live trading requires strict_mode to be enabled."
            )
