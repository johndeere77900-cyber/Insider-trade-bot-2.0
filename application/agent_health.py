"""
Health boundary for the top-level Insider Trade Bot agent.

This module provides a consistent health snapshot for startup checks,
monitoring, and external interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.agent_interface import AgentInterface


@dataclass(frozen=True)
class AgentHealthStatus:
    """Immutable health snapshot."""

    healthy: bool
    running: bool
    application_configured: bool
    trading_configured: bool
    live_trading_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "running": self.running,
            "application_configured": self.application_configured,
            "trading_configured": self.trading_configured,
            "live_trading_allowed": self.live_trading_allowed,
        }


class AgentHealth:
    """Provides health checks through the public agent interface."""

    def __init__(self, interface: AgentInterface) -> None:
        self._interface = interface

    def check(self) -> AgentHealthStatus:
        """Return the current health state."""
        result = self._interface.health()

        if not result.success or not isinstance(result.data, dict):
            return AgentHealthStatus(
                healthy=False,
                running=False,
                application_configured=False,
                trading_configured=False,
                live_trading_allowed=False,
            )

        data = result.data

        return AgentHealthStatus(
            healthy=bool(data.get("healthy", False)),
            running=bool(data.get("running", False)),
            application_configured=bool(
                data.get("application_configured", False)
            ),
            trading_configured=bool(
                data.get("trading_configured", False)
            ),
            live_trading_allowed=bool(
                data.get("live_trading_allowed", False)
            ),
        )

    def is_healthy(self) -> bool:
        """Return whether the agent currently reports healthy."""
        return self.check().healthy
