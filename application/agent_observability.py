"""
Top-level observability boundary for Insider Trade Bot 2.0.

This module combines agent status and health information into a single
read-only observability snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.agent_health import AgentHealth
from application.agent_manager import AgentManager


@dataclass(frozen=True)
class AgentObservabilitySnapshot:
    """Read-only operational snapshot."""

    status: dict[str, Any]
    health: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": dict(self.status),
            "health": dict(self.health),
        }


class AgentObservability:
    """Provides operational visibility without changing agent state."""

    def __init__(
        self,
        *,
        manager: AgentManager,
        health: AgentHealth,
    ) -> None:
        self._manager = manager
        self._health = health

    def snapshot(self) -> AgentObservabilitySnapshot:
        """Return the current status and health snapshot."""
        status = self._manager.status().to_dict()
        health = self._health.check().to_dict()

        return AgentObservabilitySnapshot(
            status=status,
            health=health,
        )

    def is_healthy(self) -> bool:
        """Return whether the current agent health check passes."""
        return self._health.is_healthy()
