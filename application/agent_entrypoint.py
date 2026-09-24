"""
Top-level process entrypoint for Insider Trade Bot 2.0.

This module provides the final application-facing startup/shutdown boundary
without implementing domain logic.
"""

from __future__ import annotations

from typing import Any, Optional

from application.agent_manager import AgentManager
from application.agent_manager_factory import create_agent_manager
from application.agent_result import AgentResult
from application.operation_guard import ApplicationOperationGuard
from application.registry import ApplicationRegistry
from application.trading_service import TradingService


class AgentEntrypoint:
    """
    Process-level entrypoint for the assembled Insider Trade Bot.

    The entrypoint receives an already-created application registry and
    runtime. It does not create database, SEC, market-data, or broker
    dependencies itself.
    """

    def __init__(
        self,
        *,
        registry: ApplicationRegistry,
        runtime: Any,
        facade: Any = None,
        controller: Any = None,
        command_parser: Any = None,
        command_service: Any = None,
        trading_service: Optional[TradingService] = None,
        operation_guard: Optional[ApplicationOperationGuard] = None,
    ) -> None:
        self._manager = create_agent_manager(
            registry=registry,
            runtime=runtime,
            facade=facade,
            controller=controller,
            command_parser=command_parser,
            command_service=command_service,
            trading_service=trading_service,
            operation_guard=operation_guard,
        )

    @property
    def manager(self) -> AgentManager:
        """Return the top-level agent manager."""
        return self._manager

    def start(self) -> AgentResult:
        """Start the agent process lifecycle."""
        return self._manager.start()

    def stop(self) -> AgentResult:
        """Stop the agent process lifecycle."""
        return self._manager.stop()

    def health(self) -> AgentResult:
        """Run a top-level health check."""
        return self._manager.health_check()

    def status(self) -> dict[str, Any]:
        """Return top-level lifecycle status."""
        return self._manager.status().to_dict()

    def handle(
        self,
        request: Any,
        *,
        context: Any = None,
    ) -> AgentResult:
        """Handle an external request through the top-level interface."""
        return self._manager.handle(
            request,
            context=context,
  )
