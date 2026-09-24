"""
Top-level manager for the Insider Trade Bot agent.

The manager provides one controlled place for starting, stopping, checking,
and accessing the assembled agent service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.agent_health import AgentHealth
from application.agent_interface import AgentInterface
from application.agent_lifecycle import AgentLifecycle
from application.agent_result import AgentResult
from application.agent_service import AgentService


@dataclass(frozen=True)
class AgentManagerStatus:
    """Current manager state."""

    started: bool
    healthy: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "started": self.started,
            "healthy": self.healthy,
        }


class AgentManager:
    """
    Coordinates the public top-level agent components.

    This manager does not implement research, signal generation, backtesting,
    risk calculations, or order execution.
    """

    def __init__(
        self,
        *,
        service: AgentService,
        interface: AgentInterface | None = None,
        health: AgentHealth | None = None,
        lifecycle: AgentLifecycle | None = None,
    ) -> None:
        self._service = service
        self._interface = interface or AgentInterface(service)
        self._health = health or AgentHealth(self._interface)
        self._lifecycle = lifecycle or AgentLifecycle(
            interface=self._interface,
            health=self._health,
        )

    @property
    def service(self) -> AgentService:
        """Return the underlying agent service."""
        return self._service

    @property
    def interface(self) -> AgentInterface:
        """Return the public interface."""
        return self._interface

    @property
    def health(self) -> AgentHealth:
        """Return the health component."""
        return self._health

    @property
    def lifecycle(self) -> AgentLifecycle:
        """Return the lifecycle component."""
        return self._lifecycle

    def start(self) -> AgentResult:
        """Start the complete agent lifecycle."""
        return self._lifecycle.start()

    def stop(self) -> AgentResult:
        """Stop the complete agent lifecycle."""
        return self._lifecycle.stop()

    def status(self) -> AgentManagerStatus:
        """Return manager-level status."""
        lifecycle_status = self._lifecycle.status()

        return AgentManagerStatus(
            started=lifecycle_status.started,
            healthy=lifecycle_status.healthy,
        )

    def health_check(self) -> AgentResult:
        """Return a standardized health result."""
        health = self._health.check()

        if not health.healthy:
            return AgentResult.failure(
                message="Agent health check failed.",
                error="agent_unhealthy",
                data=health.to_dict(),
            )

        return AgentResult.ok(
            message="Agent health check passed.",
            data=health.to_dict(),
        )

    def handle(self, request: Any, *, context: Any = None) -> AgentResult:
        """Handle an external request through the public interface."""
        return self._interface.handle(
            request,
            context=context,
      )
