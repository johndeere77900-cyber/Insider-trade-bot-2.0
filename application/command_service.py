"""
Application command service.

Translates normalized application commands into calls to the appropriate
application services.
"""

from __future__ import annotations

from typing import Any

from application.commands import (
    ApplicationCommand,
    BacktestCommand,
    PortfolioCommand,
    ResearchCommand,
    SignalCommand,
    StatusCommand,
    TradeCommand,
)
from application.errors import ApplicationRequestError
from application.registry import ApplicationRegistry
from application.result import ApplicationResult


class ApplicationCommandService:
    """Executes normalized application commands."""

    def __init__(self, registry: ApplicationRegistry) -> None:
        if registry is None:
            raise ValueError("registry is required.")

        self.registry = registry

    def execute(
        self,
        command: ApplicationCommand,
        *,
        context: Any = None,
    ) -> ApplicationResult:
        """Execute a normalized application command."""

        if not isinstance(command, ApplicationCommand):
            raise ApplicationRequestError(
                "command must be an ApplicationCommand instance."
            )

        if isinstance(command, StatusCommand):
            return ApplicationResult.ok(
                data=self.registry.get_application().status(),
                message="Application status retrieved.",
            )

        if isinstance(command, ResearchCommand):
            result = self.registry.get_application().research(
                **dict(command.parameters)
            )

            return self._from_service_result(
                result,
                success_message="Research request processed.",
            )

        if isinstance(command, SignalCommand):
            result = self.registry.get_application().signal(
                **dict(command.parameters)
            )

            return self._from_service_result(
                result,
                success_message="Signal request processed.",
            )

        if isinstance(command, BacktestCommand):
            result = self.registry.get_application().backtest(
                **dict(command.parameters)
            )

            return self._from_service_result(
                result,
                success_message="Backtest request processed.",
            )

        if isinstance(command, PortfolioCommand):
            result = self.registry.get_application().portfolio_status()

            return self._from_service_result(
                result,
                success_message="Portfolio status retrieved.",
            )

        if isinstance(command, TradeCommand):
            return self._execute_trade(
                command,
                context=context,
            )

        raise ApplicationRequestError(
            f"Unsupported application command: {command.name}"
        )

    def _execute_trade(
        self,
        command: TradeCommand,
        *,
        context: Any = None,
    ) -> ApplicationResult:
        """Execute a structured trade through the trading service."""

        trading_service = self.registry.get_trading()

        result = trading_service.execute(
            request=command.parameters["request"],
            context=context,
        )

        return self._from_service_result(
            result,
            success_message="Trading request processed.",
        )

    @staticmethod
    def _from_service_result(
        result: Any,
        *,
        success_message: str,
    ) -> ApplicationResult:
        """Convert a service response into a standard application result."""

        if isinstance(result, ApplicationResult):
            return result

        if isinstance(result, dict):
            status = str(result.get("status", "completed"))

            if status in {
                "error",
                "failed",
                "failure",
                "unavailable",
                "unauthorized",
            }:
                return ApplicationResult.failure(
                    error=str(
                        result.get(
                            "reason",
                            result.get("error", "Application operation failed."),
                        )
                    ),
                    status=status,
                    data=result,
                )

            return ApplicationResult.ok(
                data=result,
                message=success_message,
            )

        return ApplicationResult.ok(
            data=result,
            message=success_message,
    )
