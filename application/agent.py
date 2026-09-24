"""
Top-level Insider Trade Bot agent.

This module provides the main in-process agent boundary that coordinates
application services, trading services, lifecycle management, and operation
safety without duplicating domain logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from application.command_parser import ApplicationCommandParser
from application.command_service import ApplicationCommandService
from application.controller import ApplicationController
from application.facade import ApplicationFacade
from application.operation_guard import ApplicationOperationGuard
from application.registry import ApplicationRegistry
from application.result import ApplicationResult
from application.trading_service import TradingRequest, TradingService


@dataclass
class AgentStatus:
    """High-level runtime status of the agent."""

    running: bool
    application_configured: bool
    trading_configured: bool
    live_trading_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "application_configured": self.application_configured,
            "trading_configured": self.trading_configured,
            "live_trading_allowed": self.live_trading_allowed,
        }


class InsiderTradeAgent:
    """
    Top-level runtime boundary for Insider Trade Bot 2.0.

    The agent delegates business operations to the existing application
    services rather than implementing research, signals, backtesting, or
    execution logic itself.
    """

    def __init__(
        self,
        *,
        registry: ApplicationRegistry,
        runtime: Any,
        facade: Optional[ApplicationFacade] = None,
        controller: Optional[ApplicationController] = None,
        command_parser: Optional[ApplicationCommandParser] = None,
        command_service: Optional[ApplicationCommandService] = None,
        trading_service: Optional[TradingService] = None,
        operation_guard: Optional[ApplicationOperationGuard] = None,
    ) -> None:
        self.registry = registry
        self.runtime = runtime

        self.facade = facade
        self.controller = controller
        self.command_parser = command_parser
        self.command_service = command_service
        self.trading_service = trading_service
        self.operation_guard = operation_guard

    def start(self) -> None:
        """Start the application runtime."""
        self.runtime.start()

    def stop(self) -> None:
        """Stop the application runtime."""
        self.runtime.stop()

    def is_running(self) -> bool:
        """Return whether the runtime is currently running."""
        return bool(self.runtime.is_running())

    def status(self) -> AgentStatus:
        """Return a high-level status snapshot."""
        application_configured = self.registry.get_application() is not None

        try:
            trading = self.registry.get_trading()
            trading_configured = trading is not None
        except Exception:
            trading_configured = False

        live_allowed = False

        if self.operation_guard is not None:
            live_allowed = bool(
                getattr(self.operation_guard, "allow_live_trading", False)
            )

        return AgentStatus(
            running=self.is_running(),
            application_configured=application_configured,
            trading_configured=trading_configured,
            live_trading_allowed=live_allowed,
        )

    def execute_command(self, command: Any) -> ApplicationResult:
        """
        Execute an already-parsed application command.

        Command execution remains delegated to the application controller.
        """
        if self.controller is None:
            return ApplicationResult.failure(
                message="Application controller is not configured.",
                error="controller_not_configured",
            )

        try:
            result = self.controller.execute(command)
        except Exception as exc:
            return ApplicationResult.failure(
                message="Command execution failed.",
                error=str(exc),
            )

        if isinstance(result, ApplicationResult):
            return result

        return ApplicationResult.success(
            message="Command executed.",
            data=result,
        )

    def handle(self, request: Any) -> ApplicationResult:
        """
        Parse and execute an external application request.

        This is the preferred generic entry point for interfaces such as
        Telegram, CLI, or future API adapters.
        """
        if self.controller is None:
            return ApplicationResult.failure(
                message="Application controller is not configured.",
                error="controller_not_configured",
            )

        try:
            result = self.controller.handle(request)
        except Exception as exc:
            return ApplicationResult.failure(
                message="Request handling failed.",
                error=str(exc),
            )

        if isinstance(result, ApplicationResult):
            return result

        return ApplicationResult.success(
            message="Request handled.",
            data=result,
        )

    def trade(
        self,
        request: TradingRequest,
        *,
        context: Any = None,
    ) -> ApplicationResult:
        """
        Execute a structured trading request through the trading service.

        This method does not directly access a broker or exchange.
        """
        if self.trading_service is None:
            return ApplicationResult.failure(
                message="Trading service is not configured.",
                error="trading_service_not_configured",
            )

        try:
            result = self.trading_service.execute(
                request=request,
                context=context,
            )
        except Exception as exc:
            return ApplicationResult.failure(
                message="Trading request failed.",
                error=str(exc),
            )

        if isinstance(result, ApplicationResult):
            return result

        return ApplicationResult.success(
            message="Trading request processed.",
            data=result,
        )

    def health(self) -> dict[str, Any]:
        """Return runtime and configuration health information."""
        status = self.status()

        return {
            "healthy": status.application_configured,
            "running": status.running,
            "application_configured": status.application_configured,
            "trading_configured": status.trading_configured,
            "live_trading_allowed": status.live_trading_allowed,
  }
