"""
Interface boundary for external clients of the Insider Trade Bot.

External interfaces such as Telegram should interact with this boundary
instead of reaching directly into internal application components.
"""

from __future__ import annotations

from typing import Any, Optional

from application.agent_context import AgentContext
from application.agent_result import AgentResult
from application.agent_service import AgentService


class AgentInterface:
    """Stable interface for external consumers of the agent."""

    def __init__(self, service: AgentService) -> None:
        self._service = service

    @property
    def service(self) -> AgentService:
        """Return the underlying agent service."""
        return self._service

    def start(self) -> AgentResult:
        """Start the agent."""
        return self._service.start()

    def stop(self) -> AgentResult:
        """Stop the agent."""
        return self._service.stop()

    def status(self) -> AgentResult:
        """Return current agent status."""
        return self._service.status()

    def health(self) -> AgentResult:
        """Return current agent health."""
        return self._service.health()

    def handle(
        self,
        request: Any,
        *,
        context: Optional[AgentContext] = None,
    ) -> AgentResult:
        """
        Handle an external request through the agent service.

        No domain logic is implemented here.
        """
        return self._service.handle(
            request,
            context=context,
  )
