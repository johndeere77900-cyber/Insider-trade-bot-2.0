"""
Top-level agent configuration.

This module provides a dedicated configuration object for the assembled
Insider Trade Bot without replacing the existing application configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class AgentConfiguration:
    """
    Configuration for the top-level agent boundary.

    Domain-specific settings remain owned by their respective components.
    """

    name: str = "Insider Trade Bot 2.0"
    environment: str = "development"
    enabled: bool = True
    strict_mode: bool = True
    paper_trading_enabled: bool = True
    live_trading_enabled: bool = False
    telegram_enabled: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate top-level safety constraints."""

        if not self.name.strip():
            raise ValueError("Agent name must not be empty.")

        if not self.environment.strip():
            raise ValueError("Agent environment must not be empty.")

        if self.live_trading_enabled and not self.strict_mode:
            raise ValueError(
                "Live trading cannot be enabled while strict_mode is disabled."
            )

        if self.live_trading_enabled and self.environment == "development":
            raise ValueError(
                "Live trading cannot be enabled in development environment."
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a serialization-friendly configuration snapshot."""
        return {
            "name": self.name,
            "environment": self.environment,
            "enabled": self.enabled,
            "strict_mode": self.strict_mode,
            "paper_trading_enabled": self.paper_trading_enabled,
            "live_trading_enabled": self.live_trading_enabled,
            "telegram_enabled": self.telegram_enabled,
            "metadata": dict(self.metadata),
        }
