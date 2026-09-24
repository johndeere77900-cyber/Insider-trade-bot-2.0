"""
Runtime wrapper for the top-level Insider Trade Bot agent.

This module provides a controlled lifecycle boundary around the assembled
agent. It does not implement domain logic or direct broker/exchange access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.agent import InsiderTradeAgent
from application.agent_errors import AgentNotRunningError


@dataclass(frozen=True)
class AgentRuntimeStatus:
    """Runtime state snapshot."""

    running: bool
    status: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "status": dict(self.status),
        }


class AgentRuntime:
    """
    Lifecycle controller for an already-assembled InsiderTradeAgent.

    The runtime deliberately does not construct the agent's dependencies.
    """

    def __init__(self, agent: InsiderTradeAgent) -> None:
        self._agent = agent

    @property
    def agent(self) -> InsiderTradeAgent:
        """Return the managed agent."""
        return self._agent

    def start(self) -> None:
        """Start the managed agent."""
        self._agent.start()

    def stop(self) -> None:
        """Stop the managed agent."""
        self._agent.stop()

    def is_running(self) -> bool:
        """Return whether the managed agent is running."""
        return self._agent.is_running()

    def require_running(self) -> None:
        """Raise if the agent is not currently running."""
        if not self.is_running():
            raise AgentNotRunningError(
                "The Insider Trade Bot agent is not running."
            )

    def status(self) -> AgentRuntimeStatus:
        """Return runtime and agent status."""
        return AgentRuntimeStatus(
            running=self.is_running(),
            status=self._agent.status().to_dict(),
        )

    def health(self) -> dict[str, Any]:
        """Return the managed agent's health information."""
        return self._agent.health()
