"""
Lifecycle coordinator for the top-level Insider Trade Bot agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.agent_errors import AgentExecutionError
from application.agent_health import AgentHealth, AgentHealthStatus
from application.agent_interface import AgentInterface
from application.agent_result import AgentResult


@dataclass(frozen=True)
class LifecycleStatus:
    """Current lifecycle state."""

    started: bool
    healthy: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "started": self.started,
            "healthy": self.healthy,
        }


class AgentLifecycle:
    """
    Coordinates start, health verification, and shutdown of the agent.

    Domain services remain outside this class.
    """

    def __init__(
        self,
        *,
        interface: AgentInterface,
        health: AgentHealth,
    ) -> None:
        self._interface = interface
        self._health = health
        self._started = False

    def start(self) -> AgentResult:
        """Start the agent and verify its health."""
        result = self._interface.start()

        if not result.success:
            return result

        self._started = True

        health = self._health.check()

        if not health.healthy:
            self._started = False

            return AgentResult.failure(
                message="Agent started but failed health verification.",
                error="health_check_failed",
                data=health.to_dict(),
            )

        return AgentResult.ok(
            message="Agent started and passed health verification.",
            data=health.to_dict(),
        )

    def stop(self) -> AgentResult:
        """Stop the agent."""
        result = self._interface.stop()

        if not result.success:
            return result

        self._started = False

        return AgentResult.ok(
            message="Agent stopped.",
            data=self.status().to_dict(),
        )

    def health(self) -> AgentHealthStatus:
        """Return the current health snapshot."""
        return self._health.check()

    def status(self) -> LifecycleStatus:
        """Return lifecycle state."""
        return LifecycleStatus(
            started=self._started,
            healthy=self._health.is_healthy(),
        )

    def require_started(self) -> None:
        """Raise if the lifecycle has not been started."""
        if not self._started:
            raise AgentExecutionError(
                "The Insider Trade Bot agent has not been started."
    )
